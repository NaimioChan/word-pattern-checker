# word-pattern-checker

给 agent 填词用的词格校验器。词格指字数与分句，不含平仄与韵脚。支持中文、日语、韩语、英语，以及同句混排。

一个文件，无第三方依赖，Python 3.8+。

## 用法

```bash
python wpc.py hash  --spec examples/spec.txt
python wpc.py check --spec examples/spec.txt --draft examples/draft.txt
python wpc.py check --spec examples/spec.txt --draft examples/draft.txt --json
python wpc.py list  --draft examples/draft.txt
```

退出码：`0` 通过，`1` 有违例，`2` 格式错，`3` spec 被改过。

## 两个文件

`spec.txt` 由人写，定义每段的每句分几句、每句几格。

```
## verse
1 | 2/2/2
2 | 3/3 | en
```

`draft.txt` 由 agent 写，累积多个版本，只放文本。头部记录 spec 的 sha256，spec 一改就报 `spec_drift`。

```
# spec: spec.txt sha256=99e5b0b5…

## v1 2026-10-19 11:02
[verse]
1 | 夜色 | 沉入 | 水面
```

## 测试

```bash
python -m unittest discover -s tests -t .
```

格式细节、切格规则、JSON schema 全部在 [DESIGN.md](DESIGN.md)。给 agent 的操作说明在 [SKILL.md](SKILL.md)。
