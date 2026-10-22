"""投递记录表单。"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    DateTimeLocalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.validators import HttpUrl
from app.utils.constants import CHANNEL_LABELS, STATUS_LABELS, STATUS_ORDER
from app.utils.dtime import now_local


class ApplicationForm(FlaskForm):
    company_id = SelectField(
        "所属企业",
        coerce=int,
        validators=[DataRequired(message="请选择企业")],
        choices=[],
    )
    position_name = StringField(
        "职位名称",
        validators=[DataRequired(message="请填写职位名称"), Length(max=120)],
        render_kw={"placeholder": "如：Java 后端开发工程师", "autofocus": True},
    )
    job_type_id = SelectField("职位类型", coerce=int, validators=[Optional()], choices=[], default=0)
    channel = SelectField(
        "投递渠道",
        choices=[(key, label) for key, label in CHANNEL_LABELS.items()],
        default="website",
    )
    status = SelectField(
        "当前状态",
        choices=[(key, STATUS_LABELS[key]) for key in STATUS_ORDER],
        default="applied",
    )
    applied_at = DateTimeLocalField(
        "投递时间",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="请选择投递时间")],
        default=now_local,
    )
    salary_min = IntegerField(
        "月薪下限（K）",
        validators=[Optional(), NumberRange(min=0, max=1000, message="请填写 0-1000 的整数")],
        render_kw={"placeholder": "如 15"},
    )
    salary_max = IntegerField(
        "月薪上限（K）",
        validators=[Optional(), NumberRange(min=0, max=1000, message="请填写 0-1000 的整数")],
        render_kw={"placeholder": "如 25"},
    )
    resume_id = SelectField("使用简历", coerce=int, validators=[Optional()], choices=[], default=0)
    jd_url = StringField(
        "JD 链接",
        validators=[Optional(), Length(max=500), HttpUrl(max_length=500)],
        render_kw={"placeholder": "招聘页面地址，可留空"},
    )
    notes = TextAreaField(
        "备注",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "笔试题目、HR 联系方式、面试提醒…"},
    )
    submit = SubmitField("保存")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate_salary_min(self, field):
        """行内校验（跨字段）：不能把 validator 塞进类级 list，
        否则 WTForms 会复用同一个 list 对象，多次实例化后重复执行。"""
        if field.data is not None and self.salary_max.data is not None and field.data > self.salary_max.data:
            raise ValidationError("薪资下限不能大于上限")

    def to_payload(self) -> dict:
        """把表单数据整形成 Service 层需要的 dict（Service 不依赖 WTForms）。"""
        return {
            "company_id": self.company_id.data,
            "position_name": self.position_name.data,
            "job_type_id": self.job_type_id.data or None,
            "channel": self.channel.data,
            "status": self.status.data,
            "applied_at": self.applied_at.data,
            "salary_min": self.salary_min.data,
            "salary_max": self.salary_max.data,
            "resume_id": self.resume_id.data or None,
            "jd_url": self.jd_url.data,
            "notes": self.notes.data,
        }
