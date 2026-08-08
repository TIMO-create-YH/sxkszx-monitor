#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把已解析的投档线 JSON 合成一个「单文件离线查询页」。
双击 site/index.html 即可用：搜院校、筛批次、按分数排序，断网也能查。
"""

import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(ROOT, "data", "json")
SITE = os.path.join(ROOT, "site")
CST = timezone(timedelta(hours=8))


def collect():
    rows, files = [], []
    if not os.path.isdir(JSON_DIR):
        return rows, files
    for fn in sorted(os.listdir(JSON_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(JSON_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        batch = d.get("batch") or ""
        src = d.get("file", fn)
        # 从文件名补充类别信息，如 "_K美术与设计类.pdf"
        tag = src.rsplit("_", 1)[-1].replace(".pdf", "") if "_" in src else ""
        files.append({"file": src, "batch": batch, "n": len(d.get("rows", []))})
        for r in d.get("rows", []):
            rows.append([
                r.get("code", ""), r.get("school", ""),
                r.get("subject", "") or tag, r.get("group", ""),
                r.get("score", ""), batch,
                1 if r.get("vacancy") else 0,
            ])
    return rows, files


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>山西高考投档最低分 · 本地查询</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
background:#f4f6f9;color:#1b2430;padding:14px;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto}
header{background:linear-gradient(135deg,#b4232a,#e0474e);color:#fff;
padding:18px 20px;border-radius:14px;margin-bottom:14px;box-shadow:0 6px 18px rgba(180,35,42,.22)}
h1{font-size:19px;font-weight:700}
.sub{font-size:12.5px;opacity:.92;margin-top:5px}
.bar{background:#fff;padding:12px;border-radius:12px;margin-bottom:12px;
display:flex;gap:9px;flex-wrap:wrap;box-shadow:0 2px 8px rgba(0,0,0,.05)}
input,select{padding:9px 12px;border:1.5px solid #dfe4ec;border-radius:9px;
font-size:14px;outline:none;font-family:inherit}
input:focus,select:focus{border-color:#b4232a}
#q{flex:1;min-width:180px}
.stat{background:#fff;padding:9px 14px;border-radius:9px;margin-bottom:10px;
font-size:13px;color:#5a6675;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.stat b{color:#b4232a;font-size:15px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;
overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.06);font-size:13.5px}
th{background:#2c3644;color:#fff;padding:11px 9px;text-align:left;
font-weight:600;font-size:13px;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{background:#3a4757}
td{padding:9px;border-bottom:1px solid #eef1f5}
tr:hover td{background:#fff8f2}
.sc{font-weight:700;color:#b4232a;font-size:15px}
.tiny{color:#93a0b0;font-size:11px}
.pill{display:inline-block;background:#eef1f6;color:#4a5666;padding:2px 8px;
border-radius:20px;font-size:11.5px}
.vac{display:inline-block;background:#fff3e0;color:#c46a10;padding:3px 9px;
border-radius:7px;font-size:12px;font-weight:600;white-space:nowrap}
.empty{text-align:center;padding:44px;color:#93a0b0;background:#fff;border-radius:12px}
footer{margin:16px 0;text-align:center;color:#93a0b0;font-size:12px;line-height:1.8}
@media(max-width:640px){body{padding:9px}.hide-m{display:none}td,th{padding:7px 5px;font-size:12.5px}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>山西高考 · 院校专业组投档最低分</h1>
  <div class="sub">本地离线副本 · 数据更新于 __UPDATED__ · 官网挤爆也能查</div>
</header>

<div class="bar">
  <input id="q" placeholder="搜索院校名 / 院校代号，如：山西大学、1001">
  <select id="batch"><option value="">全部批次</option></select>
  <select id="subj"><option value="">全部科类</option></select>
  <select id="sort">
    <option value="def">默认顺序</option>
    <option value="hi">分数从高到低</option>
    <option value="lo">分数从低到高</option>
  </select>
  <select id="vac">
    <option value="">全部专业组</option>
    <option value="0">只看已投满（有分数）</option>
    <option value="1">只看缺额组（待征集志愿）</option>
  </select>
  <input id="mymin" type="number" placeholder="输入我的分数，筛出可冲的组" style="min-width:170px">
</div>

<div class="stat" id="stat"></div>
<div id="box"></div>

<footer>
  数据来源：山西招生考试网 www.sxkszx.cn　|　本页为自动抓取的本地缓存副本<br>
  以官方发布为准；分数格式「投档分.同分排序小分」
</footer>
</div>

<script>
const DATA = __DATA__;
const FILES = __FILES__;
const $ = s => document.querySelector(s);

// 填充下拉
const batches = [...new Set(DATA.map(r=>r[5]).filter(Boolean))].sort();
const subjects = [...new Set(DATA.map(r=>r[2]).filter(Boolean))].sort();
batches.forEach(b=>$('#batch').add(new Option(b,b)));
subjects.forEach(s=>$('#subj').add(new Option(s,s)));

function num(s){ const v=parseFloat(String(s).split('.')[0]); return isNaN(v)?-1:v; }

function render(){
  const q=$('#q').value.trim().toLowerCase();
  const b=$('#batch').value, sj=$('#subj').value, so=$('#sort').value;
  const vf=$('#vac').value, my=parseFloat($('#mymin').value);
  let rows=DATA.filter(r=>{
    if(b && r[5]!==b) return false;
    if(sj && r[2]!==sj) return false;
    if(vf!=='' && String(r[6])!==vf) return false;
    if(!isNaN(my) && !r[6] && num(r[4])>my) return false;   // 我的分够得着
    if(q && !(r[1].toLowerCase().includes(q)||r[0].includes(q))) return false;
    return true;
  });
  if(so==='hi') rows=[...rows].sort((a,c)=>num(c[4])-num(a[4]));
  if(so==='lo') rows=[...rows].sort((a,c)=>num(a[4])-num(c[4]));

  const vacN=DATA.filter(r=>r[6]).length;
  $('#stat').innerHTML = `全库 <b>${DATA.length}</b> 条投档记录`
    + `（含 <b>${vacN}</b> 个缺额组），当前筛出 <b>${rows.length}</b> 条`
    + (!isNaN(my)?`　·　已按「${my} 分」过滤出你够得着的组`:'')
    + (rows.length>800?'　·　仅显示前 800 条':'');

  if(!rows.length){
    $('#box').innerHTML='<div class="empty">没有匹配结果<br><span class="tiny">换个关键词或放宽筛选</span></div>';
    return;
  }
  let h='<table><thead><tr><th class="hide-m">代号</th><th>院校名称</th>'
      +'<th class="hide-m">科类</th><th>专业组</th><th>投档最低分</th></tr></thead><tbody>';
  rows.slice(0,800).forEach(r=>{
    const p=String(r[4]).split('.');
    const scoreCell = r[6]
      ? '<span class="vac">缺额·待征集</span>'
      : `<span class="sc">${p[0]}</span><div class="tiny">${p[1]?'小分 '+p[1]:''}</div>`;
    h+=`<tr><td class="hide-m tiny">${r[0]}</td><td><b>${r[1]}</b>`
      +`<div class="tiny">${r[5]||''}</div></td>`
      +`<td class="hide-m"><span class="pill">${r[2]||'-'}</span></td>`
      +`<td>${r[3]}</td><td>${scoreCell}</td></tr>`;
  });
  $('#box').innerHTML=h+'</tbody></table>';
}
['q','batch','subj','sort','vac','mymin'].forEach(id=>{
  $('#'+id).addEventListener('input',render);
  $('#'+id).addEventListener('change',render);
});
render();
</script>
</body></html>
"""


def build():
    rows, files = collect()
    os.makedirs(SITE, exist_ok=True)
    html = (HTML
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__FILES__", json.dumps(files, ensure_ascii=False))
            .replace("__UPDATED__", datetime.now(CST).strftime("%Y-%m-%d %H:%M")))
    out = os.path.join(SITE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[站点] 已生成 {out}（{len(rows)} 条投档记录 / {len(files)} 个数据文件）")
    return out


if __name__ == "__main__":
    build()
