#

## ensure_comment_policy.py
python scripts/ensure_comment_policy.py --help
检查现有配置，不修改文件
python scripts/ensure_comment_policy.py --check
补齐缺少的规则
python scripts/ensure_comment_policy.py --apply

功能	行为
Ruff	合并 PGH003、PGH004、RUF100 到 extend-select
Pyright	启用 reportUnnecessaryTypeIgnoreComment = "warning"
既有配置	保留其他规则，不覆盖完整配置
重复执行	幂等，不重复添加规则
配置冲突	返回错误，不强行覆盖冲突设置
ERA001	保持按需检查，不默认启用

------------------------------------------------------------------