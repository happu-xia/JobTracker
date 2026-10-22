"""业务服务层。

约定：视图（blueprints）只做「取参数 → 调 service → 渲染/跳转」，
所有校验、事务、跨表一致性都在这一层完成，便于单元测试直接覆盖。
"""

from __future__ import annotations
