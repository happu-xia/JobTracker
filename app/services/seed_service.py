"""演示数据生成器：一条命令造出一个「看起来像真实求职季」的数据集。

刻意保持确定性（固定随机种子），这样每次重建演示环境，图表形状都一致，讲解时不会翻车。
"""

from __future__ import annotations

import io
import random
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.interview import Interview
from app.models.job_type import JobType
from app.models.resume import Resume
from app.models.user import User
from app.services.auth_service import DEFAULT_JOB_TYPES
from app.services.file_storage import LocalFileStorage
from app.utils.dtime import now_local

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo1234"
DEMO_EMAIL = "demo@jobtracker.local"

COMPANIES = [
    ("腾讯科技（深圳）有限公司", "https://www.tencent.com", "互联网", "gt5000", "深圳"),
    ("阿里巴巴集团", "https://www.alibabacloud.com", "电子商务", "gt5000", "杭州"),
    ("字节跳动", "https://www.bytedance.com", "互联网", "gt5000", "北京"),
    ("美团", "https://www.meituan.com", "电子商务", "gt5000", "北京"),
    ("小米科技", "https://www.mi.com", "制造业", "gt5000", "北京"),
    ("网易", "https://www.163.com", "互联网", "gt5000", "杭州"),
    ("京东", "https://www.jd.com", "电子商务", "gt5000", "北京"),
    ("武汉光迅科技", "https://www.accelink.com", "通信", "1000_5000", "武汉"),
    ("华为技术有限公司", "https://www.huawei.com", "通信", "gt5000", "深圳"),
    ("小红书", "https://www.xiaohongshu.com", "互联网", "1000_5000", "上海"),
    ("武汉斗鱼网络", "https://www.douyu.com", "互联网", "200_1000", "武汉"),
    ("科大讯飞", "https://www.iflytek.com", "人工智能", "gt5000", "合肥"),
]

POSITIONS = {
    "后端开发": ["Java 后端开发工程师", "Python 后端开发", "服务端研发工程师", "Go 后端开发"],
    "前端开发": ["前端开发工程师", "Web 前端工程师", "React 前端开发"],
    "算法/数据": ["算法工程师（推荐）", "机器学习工程师", "数据分析师", "NLP 算法工程师"],
    "产品/运营": ["产品经理", "产品运营", "增长运营"],
    "测试/运维": ["测试开发工程师", "运维开发工程师", "SRE"],
}

CHANNELS = ["website", "referral", "campus", "boss", "liepin", "lagou", "zhilian", "other"]
CHANNEL_WEIGHTS = [25, 15, 5, 30, 8, 7, 6, 4]

# 状态分布（权重越大越常见）：让漏斗呈现出真实的递减形状
STATUS_PLAN = (
    ["applied"] * 12
    + ["viewed"] * 10
    + ["interviewing"] * 9
    + ["offer"] * 5
    + ["rejected"] * 14
    + ["withdrawn"] * 4
)


def _build_demo_pdf() -> bytes:
    """手工拼一个最小可用的 PDF（避免为演示引入 reportlab 这类重依赖）。

    结构：catalog → pages → page → content stream → font，末尾带正确的 xref 偏移表。
    """
    stream = b"BT /F1 24 Tf 72 760 Td (JobTracker Demo Resume) Tj ET\n"
    stream += b"BT /F1 12 Tf 72 730 Td (Generated for demo account. Feel free to delete.) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode("ascii")
    return bytes(out)


def _ensure_user(reset: bool) -> tuple[User, bool]:
    user = db.session.execute(
        db.select(User).where(User.username == DEMO_USERNAME)
    ).scalars().first()

    if user is None:
        user = User(username=DEMO_USERNAME, email=DEMO_EMAIL)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.commit()
        for index, (name, color) in enumerate(DEFAULT_JOB_TYPES):
            db.session.add(
                JobType(user_id=user.id, name=name, color=color, sort_order=index * 10, is_active=True)
            )
        db.session.commit()
        return user, True

    if reset:
        for model in (Interview, Application, Resume, Company, JobType):
            db.session.execute(db.delete(model).where(model.user_id == user.id))
        db.session.commit()
        for index, (name, color) in enumerate(DEFAULT_JOB_TYPES):
            db.session.add(
                JobType(user_id=user.id, name=name, color=color, sort_order=index * 10, is_active=True)
            )
        db.session.commit()
        return user, True

    return user, False


def _count(model, user_id: int) -> int:
    return db.session.execute(
        db.select(db.func.count()).select_from(model).where(model.user_id == user_id)
    ).scalar_one()


def _seed_resume(user: User) -> Resume:
    storage = LocalFileStorage(current_app.config["UPLOAD_ROOT"])
    ext = "pdf"
    meta = storage.save(io.BytesIO(_build_demo_pdf()), user.id, ext)
    resume = Resume(
        user_id=user.id,
        original_name="张三-后端开发-简历.pdf",
        stored_name=meta["stored_name"],
        rel_path=meta["rel_path"],
        ext=ext,
        mime="application/pdf",
        size_bytes=meta["size_bytes"],
        sha256=meta["sha256"],
        is_default=True,
    )
    db.session.add(resume)
    db.session.commit()
    return resume


def seed_demo_data(*, reset: bool = False) -> dict:
    random.seed(20260318)

    user, freshly_created = _ensure_user(reset)
    if not freshly_created and not reset:
        existing = _count(Application, user.id)
        if existing:
            return {
                "user": DEMO_USERNAME,
                "companies": _count(Company, user.id),
                "applications": existing,
                "interviews": _count(Interview, user.id),
                "resumes": _count(Resume, user.id),
                "skipped": True,
            }

    # ---------- 企业 ----------
    companies: list[Company] = []
    for name, website, industry, scale, city in COMPANIES:
        company = Company(
            user_id=user.id,
            name=name,
            website=website,
            industry=industry,
            scale=scale,
            city=city,
        )
        db.session.add(company)
        companies.append(company)
    db.session.commit()

    # ---------- 职位类型 ----------
    types = (
        db.session.execute(
            db.select(JobType).where(JobType.user_id == user.id).order_by(JobType.sort_order)
        )
        .scalars()
        .all()
    )
    type_by_name = {item.name: item for item in types}

    # ---------- 简历 ----------
    resume = _seed_resume(user)

    # ---------- 投递记录 ----------
    today = now_local()
    statuses = STATUS_PLAN * 3  # 足够覆盖
    random.shuffle(statuses)

    # 投递日期按指数分布向近期倾斜（求职季越临近越密集），
    # 同一天允许出现 0~4 条，这样趋势图才有起伏而不是一条平线
    days_pool: list[int] = []
    while len(days_pool) < 60:
        days_pool.append(min(int(random.expovariate(1 / 16)), 55))
    random.shuffle(days_pool)

    applications: list[Application] = []
    for index in range(60):
        company = companies[index % len(companies)]
        type_name = random.choice(list(POSITIONS.keys()))
        job_type = type_by_name.get(type_name)
        position = random.choice(POSITIONS[type_name])

        days_ago = days_pool[index]
        applied_at = (today - timedelta(days=days_ago)).replace(
            hour=random.randint(9, 21), minute=random.choice([0, 15, 30, 45])
        )

        status = statuses[index % len(statuses)]
        stage_by_status = {"applied": 1, "viewed": 2, "interviewing": 3, "offer": 4}
        stage = stage_by_status.get(status, random.choice([1, 2, 3]))

        salary_base = random.choice([12, 15, 18, 20, 25, 30])
        app_obj = Application(
            user_id=user.id,
            company_id=company.id,
            job_type_id=job_type.id if job_type else None,
            resume_id=resume.id,
            position_name=position,
            status=status,
            channel=random.choices(CHANNELS, weights=CHANNEL_WEIGHTS, k=1)[0],
            applied_at=applied_at,
            salary_min=salary_base,
            salary_max=salary_base + random.choice([3, 5, 8]),
            jd_url=None,
            notes=None,
            max_stage=stage,
        )

        if stage >= 2:
            view_delay = random.choice([0, 1, 1, 2, 3, 5])
            app_obj.first_viewed_at = applied_at + timedelta(days=view_delay)
            app_obj.response_days = view_delay

        db.session.add(app_obj)
        applications.append(app_obj)

    db.session.commit()

    # ---------- 面试记录 ----------
    interview_count = 0
    round_plan = ["first", "second", "third", "hr"]
    for app_obj in applications:
        if app_obj.max_stage < 3:
            continue

        # 面试时间必须随轮次单调递增、且不晚于今天。
        # 做法：先按「投递后 1~3 天一面，之后每轮间隔 4~8 天」生成偏移，
        # 若最后一轮超出今天，就按可用天数等比压缩整组偏移，天然保持顺序。
        rounds = random.randint(1, 3)
        offsets: list[int] = []
        cursor = random.randint(1, 3)
        for _ in range(rounds):
            offsets.append(cursor)
            cursor += random.randint(4, 8)

        days_since = max((today.date() - app_obj.applied_at.date()).days, 0)
        # min() 是单调映射：既保证轮次顺序不倒挂，又把所有面试时间压在「今天之前」
        # （否则会出现「2026-10-19 安排了一面」这种未来面试记录）
        now = now_local()
        schedule_days = [min(off, days_since) for off in offsets]

        for order, offset in enumerate(schedule_days):
            # 同一天多轮面试用分钟错开，时间线才不会看起来像重复数据
            scheduled = min(app_obj.applied_at + timedelta(days=offset, minutes=90 * order), now)
            is_last = order == len(schedule_days) - 1
            if not is_last:
                result = random.choices(["passed", "failed"], weights=[85, 15])[0]
            else:
                result = (
                    "passed"
                    if app_obj.max_stage >= 4
                    else random.choices(["pending", "passed", "failed"], weights=[35, 45, 20])[0]
                )
            db.session.add(
                Interview(
                    user_id=user.id,
                    application_id=app_obj.id,
                    round=round_plan[order % len(round_plan)],
                    scheduled_at=scheduled,
                    result=result,
                    feedback=random.choice(
                        [
                            "八股为主，问了 JVM 内存模型和 GC；算法题是二叉树层序遍历。",
                            "项目深挖，重点问了我做的这个求职系统的表设计和索引。",
                            "主管面偏场景题：如何设计一个高并发投递状态同步方案。",
                            "HR 面聊了职业规划与期望薪资，氛围轻松。",
                            None,
                        ]
                    ),
                )
            )
            interview_count += 1
    db.session.commit()

    return {
        "user": DEMO_USERNAME,
        "companies": _count(Company, user.id),
        "applications": _count(Application, user.id),
        "interviews": interview_count,
        "resumes": _count(Resume, user.id),
        "skipped": False,
    }
