# crawl-delta 中文说明

在部署 robots.txt 前，用经过审查的“旧行为 → 新行为”契约验证具体 URL 和爬虫。
可发现上线后误封整站、意外开放路径，以及旧策略已与预期不符的问题。全程离线。

需要 Python 3.11 以上，匹配规则使用固定版本 Protego 0.7.0，没有复制第三方实现。
在虚拟环境安装后运行真实示例：

```sh
python -m pip install .
python examples/demo.py
crawl-delta --before examples/before.txt --after examples/after.txt --contract examples/contract.json --format json
```

Windows 和 macOS/Linux 的明确虚拟环境路径见 [英文说明](README.md)。
演示分别验证计划开放成功和整站误封失败。契约每项包含唯一 ID、agent、具体 path、
before 和 after 两个布尔预期；不是只验证新文件，也不会自动将观测结果当成正确答案。

退出码 0 表示全部用例的前后决策均符合预期；1 表示行为不符；2 表示输入错误。
默认报告只显示 ID、布尔决策、变化类型、统计和输入指纹，不显示 URL、路由及爬虫值。
如确需在 JSON 中查看位置，显式加 `--include-locations`。ID 和哈希也可能透露信息。

限制：每个策略最多 512 KiB，契约最多 2 MiB / 5,000 条用例；超限拒绝处理。
只证明列出的有限用例，不证明整个站点的所有 URL。它不是严格语法检查器，不处理
获取 robots.txt 时的 HTTP 状态、重定向和缓存，也不预测 SEO 效果。robots.txt 本身不是访问控制。
对不可信策略应另设 CI 任务超时。源文件不修改，无持久配置；卸载执行
`python -m pip uninstall crawl-delta`，删除虚拟环境可一并清理依赖。
