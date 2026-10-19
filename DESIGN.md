# word-pattern-checker 设计契约 v0.1

给 agent 填词用的词格校验器。词格指字数与分句，不含平仄与韵脚。支持中、日、韩、英，以及同句混排。

## 形态与硬约束

- 一个无第三方依赖的 Python 3 文件 `wpc.py`，标准库之外不引入任何包。
- 同时是库和 CLI：核心函数 `check(spec_text, draft_text, version=None) -> Report` 纯函数，无 IO、无全局状态、可单测。
- **只读**。`wpc.py` 永不写文件，不回写状态，不自动修复。所有结论走 stdout，修改由 agent 自己做。
- 输出给人看时可读，给 agent 一律 `--json`。
- 退出码是契约的一部分：

| 码 | 含义 |
|---|---|
| 0 | 全部通过 |
| 1 | 有违例（字数/分句/无法归类） |
| 2 | 用法或解析错误（spec/draft 格式坏、版本不存在） |
| 3 | spec 被改动（sha256 与 draft 记录不符） |

## 文件角色

两个文件，职责不重叠。

`spec.txt` 由人写、agent 只读，定义格数与语言。
`draft.txt` 由 agent 写，累积多个版本，只放文本。

原因：格数只有一个来源；agent 返工只改文本，不会顺手改格数来自证通过。`draft.txt` 头部记录 spec 的 sha256，spec 一旦被改，checker 直接 exit 3，让 agent 回来问人。

## spec.txt 格式

```
# 可选全局键值，缺省用默认值
lang: mixed
latin: syllable
punct: ignore
digits: each

## s1
1 | 5/7 | ja
2 | 4/4 | zh

## s2
1 | 2/1/2 | en
2 | 3/3
```

规则：

- `#` 开头是注释，空行忽略。
- 全局键 `lang` / `latin` / `punct` / `digits`，出现在第一个 `## ` 之前。
- 段头 `## <段名>`，段名任意字符串（`s1`、`verse`、`chorus`）。
- 句行 `<句号> | <格数> | <lang>`。格数用 `/` 分隔，每项是该分句的格数。`<lang>` 可省略，省略时用全局 `lang`。
- 句号在同一段内唯一；checker 按 `(段名, 句号)` 对齐 spec 与 draft。
- 格数项为 0 表示该分句留空（整句无字也算通过）。

## draft.txt 格式

```
# spec: spec.txt sha256=3f9a1c...

## v1 2026-10-19 10:20
[s1]
1 | さくら さくら やよいの
2 | 春风又绿江南岸

[s2]
1 | Hold me tight
2 | 明月何时照我还

## v2 2026-10-19 10:34
...
```

规则：

- 第一行必须是 `# spec: <文件名> sha256=<64 位 hex>`，缺失即 exit 2。
- 版本头 `## <标签>`，标签与之后内容到下一个版本头为止。日期是可选的附加 token，解析时忽略标签后的其余内容。
- 段标记 `[<段名>]` 单独一行，与 spec 的段名对齐。缺段、多段都算解析错。
- 句行 `<句号> | <文本>`。文本里的空格仅作排版，校验时折叠。
- `|` 是分句分隔符，全角 `｜` 等价。
- 某句可缺省（尚未填写），算 `too_few`；句号在 spec 中不存在算 exit 2。
- `--version` 不指定时取文件中最靠后的版本头。

## 切格规则

计数前先做两件事：

1. 折叠空白。`\t`、半角空格、全角空格 U+3000 一律视作分隔，不占格。
2. 对每个分句的文本做 NFC 规范化，只用于计数；输出里另存原文。

语言分支按 spec 的 `<lang>`；`mixed` 时逐字符判定：汉字与假名走 CJK 规则，谚文音节走韩语规则，拉丁字母连续段走 `latin` 规则，数字串走 `digits` 规则。

### 中文 zh

- 每个汉字 1 格（`unicodedata` 的 `Lo` 且落在 CJK 区间）。
- 数字：`digits: each` 时每个数字字符 1 格，`digits: word` 时整串算 1 格。
- 叠字符号 `々` 记 1 格。

### 日语 ja

- 每个假名（平假名、片假名）1 格。
- 小写假名 `ゃゅょぁぃぅぇぉ` 与 `ゎ` 紧跟在假名后时，与前一字符合并为一格，`cells` 里显示为 `きゃ` 这样的字符串。
- `っ`（促音）、`ー`（长音符 U+30FC）、`ん`、`ッ`、`ン` 各占 1 格。
- `ー` 的 Unicode 类别是 `Lm`，切格函数不得把它当成标点剔除。同理 `々`、`,` 以外的修饰字符。
- 半角片假名（`ｷｬ`）在计数前做 NFKC，结果与全角一致。
- IVS 变体选择符（U+E0100–U+E01EF、U+FE00–U+FE0F）不占格，从计数流里丢弃。

### 韩语 ko

- 先 NFC，再每音节（谚文音节块 U+AC00–U+D7A3）1 格。
- 输入为 NFD（分解的初声/中声/终声）时必须得到与 NFC 相同的格数，这是硬性等价要求。
- 单独出现的谚文字母（U+1100–U+11FF）算 `unclassified`。

### 英语 en

按 `latin` 键，`syllable`（默认）、`letter`、`word` 三档。前两档之外还有连字符语义：

- 文本中的连字符（`-`、U+2010、U+2011）先作为显式音节边界切开，再逐段计数。因此 `Spi-der-Man` 恒为 3 格，`well-known` 也自然算 2 格。
- `letter`：每个拉丁字母 1 格，撇号忽略（`don't` 算 4 格）。
- `word`：每个词 1 格。
- `syllable`：见下节算法，结果带 `estimated: true`。

## 英语音节算法（syllable 模式）

启发式规则，词表兜底，不追求词典级准确。

```
function syllables(word):
    w = lower(word)，去掉首尾非字母
    if w in EXCEPTIONS: return EXCEPTIONS[w]     # 高频词表，约 200 条
    n = 0
    for 每个元音序列 (a e i o u y):
        n += 1
        if 该序列是词尾的 e 且 词长 > 2 且 前面是辅音:
            n -= 1                                # 静音 e：make → 1
    if w 以 "le" 结尾 且 前一字符是辅音:
        n += 1                                    # table, little
    if w 以 "es" 或 "ed" 结尾 且 去掉后词干仍可读:
        if 前一个字符是 d/t 时的 "ed"，或 s/x/z/ch/sh 后的 "es":
            n -= 0                                # 保留
        else:
            n -= 1                                # walked, wants
    return max(1, n)
```

`EXCEPTIONS` 至少覆盖：one two three four eight nine eleven twelve, every evening business family beautiful, fire hour our flower power, science quiet poem cruel, people little, i a the, 以及 -tion/-sion 结尾词。每个词一经发现切错，就补进表里，表本身是可提交的数据文件（`word_exceptions.py` 或内嵌 dict）。

`syllable` 模式下每句返回 `estimated: true`。需要精确时用户可在文本里写连字符手工钉死，checker 不再猜。

## 标点与无法归类的字符

`punct: ignore`（本项目默认，已定）：所有 Unicode 类别以 `P` 开头的字符都不占格，不进 `cells`。ASCII 与全角标点一视同仁。

`punct: count` 保留为选项，但默认关闭，测试只覆盖 `ignore`。

连字符例外：在 `latin` 分支里它先被当作音节边界消费掉，不会被当成标点丢弃。因此 `Spi-der-Man` 与 `Spi der Man` 在音节模式下的格数不同，这是预期行为。

无法归类的字符：emoji 序列（含 ZWJ 组合）、未定义谚文字母、其他 `So` / `Co` 字符。默认宽松，算 1 格并在该句的 `warnings` 里记 `unclassified`。`--strict` 时升级为违例。

## CLI

```
python wpc.py check --spec spec.txt --draft draft.txt [--version v2] [--json] [--explain] [--strict]
python wpc.py list --draft draft.txt                 # 列出所有版本标签
python wpc.py hash --spec spec.txt                   # 算 sha256，供写 draft 头
```

- `check` 默认只查最后一版；`--version` 指定标签；`--version all` 查全部并按版本分别输出。
- `--json` 输出单个 JSON 对象到 stdout，其余一切走 stderr。schema 见下。
- `--explain` 输出人读的分句表，逐格对齐，便于肉眼比对分句断点。

## JSON 输出

```json
{
  "ok": false,
  "spec": {"file": "spec.txt", "sha256": "3f9a1c...", "drift": false},
  "version": "v2",
  "violations": [
    {"section": "s1", "line": "1", "lang": "ja",
     "kind": "too_many", "segment": 2,
     "expected": 5, "actual": 6,
     "cells": ["さ","く","ら","の","や"],
     "text": "さくらのやよい"}
  ],
  "warnings": [
    {"section": "s2", "line": "1", "kind": "unclassified", "cell": "🎵"}
  ],
  "summary": {"lines_checked": 4, "lines_ok": 3, "violations": 1}
}
```

`kind` 取值固定为：`too_many`、`too_few`、`seg_count_mismatch`、`unclassified`、`estimated`（后者只出现在 warnings）。agent 依此决定怎么改，不要用自然语言描述原因。

`cells` 是该分句的逐格数组，合为一格的多码位字符显示为一个字符串。这是 agent 定位偏差的唯一依据，不能省。

`spec.drift` 为 true 时 `ok` 恒 false，退出码 3，`violations` 为空，另有 `"error": "spec_drift"` 字段。

## 测试矩阵

`tests/` 用标准库 `unittest` 或 `pytest`，全部参数化在 golden case 上。

| 组 | 用例 |
|---|---|
| zh | 全角标点、数字串、中英混排、含空格、`々` |
| ja | 拗音 `きゃ`、促音 `っ`、长音 `ー`、拨音 `ん`、半角 `ｷｬ`、IVS |
| ko | 同一文本 NFC 与 NFD 输入格数必须相等、孤立字母报 unclassified |
| en | `don't`、`well-known`、`Spi-der-Man`、数字、全大写、`the` |
| mixed | `Baby 别走`、`I love 東京`、emoji、零宽字符 |
| 结构 | 版本缺失、版本乱序、段名不匹配、句号越界、sha256 不符 |

硬断言清单：

1. 同一句的 NFC 与 NFD 形式格数相同（zh/ja/ko 各一条）。
2. `きゃ` 恒为 1 格，`きよう` 为 3 格。
3. `Spi-der-Man` 在 `syllable` 模式下恒为 3。
4. 标点在 `punct: ignore` 下无论全角半角都不改变格数。
5. 任何输入都不抛异常，坏格式转成 exit 2 并给出带行号的错误信息。

## 里程碑

| 阶段 | 范围 | 完成标准 |
|---|---|---|
| M1 | spec/draft 解析、zh + en、CLI、JSON | 结构组与 zh/en 组测试全绿 |
| M2 | ja 切格（拗音/促音/长音/IVS） | ja 组全绿，NFC/NFD 等价断言通过 |
| M3 | ko、mixed 逐字符分支 | ko/mixed 组全绿 |
| M4 | `--explain`、`word_exceptions` 词表、供 agent 用的 SKILL.md | 一个真实中英混排歌词跑通全流程 |

## 非目标

- 不做平仄与韵脚判定。多语言下韵书成本远大于收益，交给 agent 的提示词与人耳。
- 不做自动改写、不改 draft。
- 不做 GUI、不做服务端。
- 不做完整 UAX #29 字形簇算法，只覆盖本文件列出的语言范围。
