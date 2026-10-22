"""简历上传测试：五层校验、默认唯一性、磁盘文件生命周期、路径安全。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.services import resume_service
from app.utils.errors import BusinessError, ConflictError, NotFoundError, ValidationError
from tests.factories import make_resume


def _file(data: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=filename, content_type="application/octet-stream")


class TestUpload:
    def test_pdf_uploaded_and_stored(self, app, user, make_pdf_bytes):
        resume = resume_service.upload(user, _file(make_pdf_bytes(), "张三-简历.pdf"))
        assert resume.ext == "pdf"
        assert resume.is_default is True  # 第一份自动成为默认
        assert resume.original_name == "张三-简历.pdf"
        # 磁盘文件名是 UUID，原始中文名不进入路径
        assert resume.stored_name.endswith(".pdf")
        assert len(resume.stored_name.split(".")[0]) == 32
        assert Path(app.config["UPLOAD_ROOT"], resume.rel_path).is_file()

    def test_fake_pdf_by_magic_bytes_rejected(self, app, user):
        """把 exe 改名成 pdf：扩展名过了，魔数过不了。"""
        with pytest.raises(ValidationError) as exc:
            resume_service.upload(user, _file(b"MZ\x90\x00\x03\x00\x00\x00", "简历.pdf"))
        assert "文件内容与扩展名不匹配" in exc.value.message

    def test_disallowed_extension_rejected(self, app, user):
        with pytest.raises(ValidationError):
            resume_service.upload(user, _file(b"%PDF-1.4", "简历.exe"))

    def test_empty_file_rejected(self, app, user):
        with pytest.raises(ValidationError):
            resume_service.upload(user, _file(b"", "空文件.pdf"))

    def test_oversize_rejected(self, app, user):
        big = b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024)
        with pytest.raises(ValidationError) as exc:
            resume_service.upload(user, _file(big, "超大.pdf"))
        assert "超出上限" in exc.value.message

    def test_docx_requires_real_container(self, app, user):
        fake = io.BytesIO()
        with zipfile.ZipFile(fake, "w") as zf:
            zf.writestr("hello.txt", "not a docx")
        with pytest.raises(ValidationError):
            resume_service.upload(user, _file(fake.getvalue(), "简历.docx"))

        real = io.BytesIO()
        with zipfile.ZipFile(real, "w") as zf:
            zf.writestr("word/document.xml", "<w:document/>")
        resume = resume_service.upload(user, _file(real.getvalue(), "真简历.docx"))
        assert resume.ext == "docx"

    def test_duplicate_content_rejected(self, app, user, make_pdf_bytes):
        data = make_pdf_bytes()
        resume_service.upload(user, _file(data, "第一份.pdf"))
        with pytest.raises(ConflictError) as exc:
            resume_service.upload(user, _file(data, "重复.pdf"))
        assert "内容完全相同" in exc.value.message
        # 重复文件不应在磁盘留下垃圾
        assert len(resume_service.list_resumes(user.id)) == 1


class TestDefault:
    def test_only_one_default_at_a_time(self, app, user, make_pdf_bytes):
        first = resume_service.upload(user, _file(make_pdf_bytes("A"), "A.pdf"))
        second = resume_service.upload(user, _file(make_pdf_bytes("B"), "B.pdf"))
        assert second.is_default is False

        resume_service.set_default(second)
        resumes = resume_service.list_resumes(user.id)
        assert sum(1 for r in resumes if r.is_default) == 1
        assert resume_service.default_resume(user.id).id == second.id
        assert first.id != second.id

    def test_upload_with_set_default_flag(self, app, user, make_pdf_bytes):
        resume_service.upload(user, _file(make_pdf_bytes("A"), "A.pdf"))
        second = resume_service.upload(user, _file(make_pdf_bytes("B"), "B.pdf"), set_default=True)
        assert second.is_default is True


class TestDelete:
    def test_delete_removes_file_and_record(self, app, user, make_pdf_bytes):
        resume = resume_service.upload(user, _file(make_pdf_bytes(), "待删.pdf"))
        path = Path(app.config["UPLOAD_ROOT"], resume.rel_path)
        assert path.is_file()

        resume_service.delete(resume)
        assert not path.exists()
        assert resume_service.list_resumes(user.id) == []

    def test_delete_keeps_application_but_unbinds(self, app, user, make_pdf_bytes):
        from tests.factories import make_application, make_company

        resume = resume_service.upload(user, _file(make_pdf_bytes(), "被引用.pdf"))
        company = make_company(user.id, "公司")
        app_obj = make_application(user.id, company.id, resume_id=resume.id)

        resume_service.delete(resume)
        db.session.refresh(app_obj)
        assert app_obj.resume_id is None  # ON DELETE SET NULL
        assert app_obj.position_name  # 投递记录仍在


class TestAccess:
    def test_path_traversal_blocked(self, app, user, make_pdf_bytes):
        resume = resume_service.upload(user, _file(make_pdf_bytes(), "正常.pdf"))
        resume.rel_path = "../../windows/win.ini"  # 模拟路径被污染
        db.session.commit()

        with pytest.raises(BusinessError):
            resume_service.open_stream(resume)

    def test_other_user_cannot_download(self, app, user, other_user, make_pdf_bytes):
        resume = resume_service.upload(user, _file(make_pdf_bytes(), "私有.pdf"))
        with pytest.raises(NotFoundError):
            resume_service.get_or_404(other_user.id, resume.id)


class TestRoutes:
    def test_upload_page_renders(self, auth_client):
        assert auth_client.get("/resumes/upload").status_code == 200

    def test_upload_via_form(self, auth_client, user, make_pdf_bytes):
        response = auth_client.post(
            "/resumes/upload",
            data={"file": (io.BytesIO(make_pdf_bytes()), "my-resume.pdf"), "set_default": "1"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert len(resume_service.list_resumes(user.id)) == 1

    def test_preview_returns_pdf_inline(self, auth_client, app, user):
        resume = make_resume(app, user.id, name="预览.pdf")
        response = auth_client.get(f"/resumes/{resume.id}/preview")
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.headers["Content-Disposition"].startswith("inline")

    def test_download_has_attachment_and_utf8_name(self, auth_client, app, user):
        resume = make_resume(app, user.id, name="张三-简历.pdf")
        response = auth_client.get(f"/resumes/{resume.id}/download")
        assert response.status_code == 200
        disposition = response.headers["Content-Disposition"]
        assert "attachment" in disposition
        assert "filename*=UTF-8''" in disposition

    def test_set_default_via_route(self, auth_client, app, user):
        make_resume(app, user.id, name="A.pdf")
        second = make_resume(app, user.id, name="B.pdf", is_default=False)

        auth_client.post(f"/resumes/{second.id}/default", follow_redirects=True)
        assert resume_service.default_resume(user.id).id == second.id

    def test_resume_list_page(self, auth_client, app, user):
        make_resume(app, user.id, name="列表页.pdf")
        response = auth_client.get("/resumes")
        assert response.status_code == 200
        assert "列表页.pdf".encode() in response.data
