# 领域文档

工程技能探索代码前，怎么消费本仓库的领域文档。

## 探索前先读

- 根目录 `GLOSSARY.md`；若存在 `GLOSSARY-MAP.md`，按它指向读相关上下文的 `GLOSSARY.md`。
- `docs/adr/`：读涉及待改区域的 ADR。

文件不存在就静默跳过，不要提示缺失，也不要建议提前创建。`/domain-modeling`（经 `/grill-with-docs`、`/improve-codebase-architecture` 触达）会在术语或决策真正定下来时才惰性创建。

## 文件结构

本仓库是单上下文（single-context）：

```
/
├── GLOSSARY.md          ← 词格、分句、格、spec、draft、漂移…按需建立
├── docs/adr/
│   ├── 0001-heuristic-syllables.md
│   └── 0002-readonly-checker.md
├── DESIGN.md            ← 已存在的设计契约，ADR 与它冲突时以裁决为准
└── wpc.py
```

## 用词表里的词

产出里出现领域概念（issue 标题、重构提案、假设、测试名）时，用 `GLOSSARY.md` 定义的说法，别漂到它明确避开的同义词。

需要的概念词表里没有，是个信号：要么你在造项目不用的词（再想想），要么确有缺口（记下来给 `/domain-modeling`）。

本项目的核心词暂定：**格**（cell，一个计数单位）、**分句**（segment，`|` 切开的单位）、**句**（line，spec 里一行）、**段**（section，`## <段名>`）、**spec**（人写的格数定义）、**draft**（agent 写的多版本文本）、**漂移**（drift，spec 的 sha256 与 draft 记录不符）。

## 标出 ADR 冲突

产出与既有 ADR 冲突时，明说，不要偷偷覆盖：

> _与 ADR-0007（只读 checker）冲突，但值得重开，因为……_
