"""企业表单。"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.validators import HttpUrl
from app.utils.constants import INDUSTRY_OPTIONS, SCALE_LABELS


class CompanyForm(FlaskForm):
    name = StringField(
        "企业名称",
        validators=[DataRequired(message="请填写企业名称"), Length(max=100, message="名称不能超过 100 字")],
        render_kw={"placeholder": "如：腾讯科技（深圳）有限公司", "autofocus": True},
    )
    website = StringField(
        "企业官网",
        validators=[Optional(), Length(max=255), HttpUrl()],
        render_kw={"placeholder": "www.example.com 或 https://example.com"},
    )
    industry = StringField(
        "所属行业",
        validators=[Optional(), Length(max=50)],
        render_kw={"list": "industryOptions", "placeholder": "可从下拉中选择，也可自定义"},
    )
    scale = SelectField(
        "人员规模",
        choices=[("", "未填写")] + [(key, label) for key, label in SCALE_LABELS.items()],
        validators=[Optional()],
        default="",
    )
    city = StringField(
        "城市",
        validators=[Optional(), Length(max=50)],
        render_kw={"placeholder": "如：武汉、深圳"},
    )
    notes = TextAreaField(
        "备注",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "办公地点、投递注意点、内推人…"},
    )
    submit = SubmitField("保存")

    @property
    def industry_options(self) -> list[str]:
        return INDUSTRY_OPTIONS
