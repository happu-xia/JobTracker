"""面试 / 职位类型 / 简历上传表单。"""

from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    DateTimeLocalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.validators import ColorHex
from app.utils.constants import ALLOWED_EXTENSIONS, RESULT_LABELS, ROUND_LABELS
from app.utils.dtime import now_local


class InterviewForm(FlaskForm):
    round = SelectField(
        "面试轮次",
        choices=[(key, label) for key, label in ROUND_LABELS.items()],
        default="first",
    )
    scheduled_at = DateTimeLocalField(
        "面试时间",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="请选择面试时间")],
        default=now_local,
    )
    result = SelectField(
        "面试结果",
        choices=[(key, label) for key, label in RESULT_LABELS.items()],
        default="pending",
    )
    feedback = TextAreaField(
        "面经 / 复盘",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "问了哪些问题、哪里答得不好、下次怎么改"},
    )
    submit = SubmitField("保存面试记录")

    def to_payload(self) -> dict:
        return {
            "round": self.round.data,
            "scheduled_at": self.scheduled_at.data,
            "result": self.result.data,
            "feedback": self.feedback.data,
        }


class JobTypeForm(FlaskForm):
    name = StringField(
        "类型名称",
        validators=[DataRequired(message="请填写类型名称"), Length(max=50, message="不能超过 50 字")],
        render_kw={"placeholder": "如：后端开发、算法工程师、产品经理", "autofocus": True},
    )
    color = StringField(
        "图表颜色",
        validators=[Optional(), ColorHex()],
        default="#0d6efd",
        render_kw={"type": "color", "class": "form-control form-control-color"},
    )
    sort_order = IntegerField(
        "排序值",
        validators=[Optional(), NumberRange(min=0, max=9999, message="请填写 0-9999 的整数")],
        default=0,
        render_kw={"placeholder": "越小越靠前，留空自动排到末尾"},
    )
    submit = SubmitField("保存")


class ResumeUploadForm(FlaskForm):
    file = FileField(
        "简历文件",
        validators=[
            FileRequired(message="请选择要上传的文件"),
            FileAllowed(list(ALLOWED_EXTENSIONS), message="仅支持 PDF / DOC / DOCX 格式"),
        ],
    )
    set_default = SelectField(
        "设为默认简历",
        choices=[("0", "否"), ("1", "是")],
        default="0",
    )
    submit = SubmitField("上传")

    @property
    def as_default(self) -> bool:
        return self.set_default.data == "1"
