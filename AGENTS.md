# AGENTS.md

word-pattern-checker：给 agent 填词时校验词格的 CLI。词格 = 字数 + 分句，不含平仄与韵脚。支持中、日、韩、英与同句混排。

## 权威文档

`DESIGN.md` 是唯一契约（spec/draft 格式、切格规则、JSON schema、退出码、测试矩阵、里程碑）。本文与它冲突时以 `DESIGN.md` 为准；要改行为先改 `DESIGN.md`，再改代码与测试。

## 栈与命令

- Python 3，只用标准库。不引入第三方包，不建 venv 以外的依赖清单。
- CLI 入口：`python wpc.py check --spec spec.txt --draft draft.txt --json`
- 测试：`python -m pytest tests/`（M1 起存在；无 pytest 时 `python -m unittest discover tests`）

## 铁律

1. 单文件 `wpc.py`，库里所有逻辑可 import。
2. `check(spec_text, draft_text, version=None) -> Report` 是纯函数：无 IO、无全局可变状态、可单测。
3. 只读。`wpc.py` 永不写文件、不回写 PASS/FAIL、不自动修复。
4. 退出码是契约：0 通过 / 1 有违例 / 2 用法或解析错 / 3 spec 漂移。改这套码等于破坏下游 agent 的分支逻辑。
5. `--json` 时 stdout 只放一个 JSON 对象，其余全部走 stderr。
6. `violations[].kind` 只用 `too_many`、`too_few`、`seg_count_mismatch`、`unclassified` 四个值；`estimated` 只出现在 `warnings`。
7. `cells` 数组必留，它是 agent 定位偏差的唯一依据。

## 禁区

- 不靠修改 `spec.txt` 让检查通过。spec 是人的输入，checker 只比对 sha256。
- 不在切格前丢失原文：NFC/NFKC 只用于计数，输出里的 `text` 保留原样。
- 不为「聪明」加自动改写、GUI、服务端、完整 UAX #29 实现（见 `DESIGN.md` 非目标）。

## Agent skills

### Issue tracker

本仓库的 issue 与 spec 都在 GitHub Issues，用 `gh` CLI 操作。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用默认五个 triage 角色标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文（single-context）：根 `GLOSSARY.md` + `docs/adr/`，按需创建。见 `docs/agents/domain.md`。
