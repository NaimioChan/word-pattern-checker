---
name: word-pattern-checker
description: Use when filling lyrics into a fixed 词格 (syllable/cell pattern). Validates 字数与分句 for zh/ja/ko/en, returns per-segment cell arrays, never edits files.
---

# word-pattern-checker

词格 = 每句的分句数与每个分句的格数。不含平仄、不含韵脚。这个工具只做一件事：告诉你哪一句、哪个分句、哪一格对不上。

## 什么时候用

用户给了词格（`spec.txt`）要你填词，或者要你在已有稿子上改版本。**不要靠数数**：中文标点、日语拗音、韩语 NFD、英文音节，模型数必错。一律调这个工具。

## 三个命令

```bash
python wpc.py hash  --spec spec.txt                     # 写 draft 头要用
python wpc.py list  --draft draft.txt                   # 看已有版本
python wpc.py check --spec spec.txt --draft draft.txt --json
```

`check` 默认查最后一版；`--version v3` 查指定版；`--version all` 查全部。

## 文件分工

- `spec.txt` 人写，你**只读**，任何情况下不要改它。改了它 checker 会 exit 3。
- `draft.txt` 你写，只放文本，几个版本按顺序往下叠。

draft 的第一行必须是 spec 的指纹：

```
# spec: spec.txt sha256=<python wpc.py hash --spec spec.txt 的输出>
```

## 循环

1. `hash` 拿指纹，写出 v1 的帧。
2. `check --json`。
3. 读 `violations`，按 `kind` 改：
   - `too_many` / `too_few` → 该分句加字或减字，`segment` 是第几个分句（1 起）
   - `seg_count_mismatch` → `|` 的数量和 spec 对不上，先修分句
   - `unclassified` → 有 emoji 或异体字符混进格子里，换掉
4. 改完写一个新版本头，重跑。重复到 `ok: true`。

## 退出码（用它分支，不要读自然语言）

| 码 | 意思 | 你该做什么 |
|---|---|---|
| 0 | 通过 | 交付这一版 |
| 1 | 有违例 | 按 violations 改，出新版 |
| 2 | 参数或格式错 | 先修文件格式，别猜 |
| 3 | spec 被改过 | 停。问用户，不要自己重算 sha256 |

## JSON 里真正有用的字段

- `violations[].section` / `.line` / `.segment`：定位，段名和句号都是 spec 里的原文。
- `violations[].cells`：这一分句实际被切成了哪些格。数不对时看它，比自己重数字符可靠。
- `violations[].text`：去掉首尾空白后的原文。
- `warnings[].kind == "estimated"`：英文音节是估算。用户在字里写了连字符（`Spi-der-Man`）就按用户的切，不要改。

## 硬规矩

- 不要为了让检查通过而改 spec、改 draft 头的 sha256。
- 不要在 draft 里写 PASS/FAIL，状态由 checker 输出，写进文件只会让下一次判断失真。
- 空格在中文段里只是排版；英文段里是词界，别删。
