"""Build an HTML catalog of BVH/blend assets and separate ZIP downloads.

python build_catalog.py --plan PLAN --output SITE --records-dir RECORDS [--zip --release-dir RELEASES] [--verify]
Run export_asset.py with the prepared jobs before building. Render pixels are
preserved while local metadata is removed; six-item sheets use Pillow.
"""
import argparse
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import posixpath
from pathlib import Path
import shutil
import urllib.parse
import zipfile
from publication_privacy import clean_file, clean_json, write_json as privacy_json, audit_tree

CSS='''
:root{color-scheme:light;--ink:#1b2a32;--muted:#5a6b75;--line:#dce4e6;--accent:#076776;--accent-hover:#004b56;--paper:#f4f6f5;--card-bg:#ffffff}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue","Hiragino Sans","Yu Gothic UI","Meiryo",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:3px}
a:hover{color:var(--accent-hover)}
header{border-bottom:1px solid var(--line);background:#fff;position:sticky;top:0;z-index:10}
nav{max-width:1200px;margin:auto;padding:16px 24px;display:flex;gap:24px;align-items:center;flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.025em;margin-right:auto;text-decoration:none;color:var(--ink);font-size:17px}
main{max-width:1200px;margin:auto;padding:42px 24px 80px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.3;margin:10px 0 18px;letter-spacing:-.03em}
h2{font-size:24px;line-height:1.35;margin:32px 0 16px;letter-spacing:-.02em}
h3{font-size:18px;margin:0 0 4px}
p{margin:12px 0}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.14em;color:var(--accent);text-transform:uppercase}
.lead{max-width:820px;color:var(--muted);font-size:17px;line-height:1.7}
.stats{display:flex;gap:36px;flex-wrap:wrap;margin:32px 0}
.stat strong{font-size:32px;display:block;line-height:1.2;color:var(--ink)}
.stat span{font-size:13px;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}
.card{background:var(--card-bg);border:1px solid var(--line);border-radius:14px;overflow:hidden;text-decoration:none;color:var(--ink);display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s,border-color .2s}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,0.06);border-color:#b8c7cb}
.card img{width:100%;height:auto;aspect-ratio:1.035;object-fit:cover;display:block;background:#eef1f2}
.card .body{padding:20px;display:flex;flex-direction:column;flex:1}
.card h2{font-size:20px;margin:0 0 8px}
.card p{font-size:14px;color:var(--muted);line-height:1.6;margin:0 0 16px;flex:1}
.count{float:right;color:var(--accent);font-weight:800;font-size:15px}
.status{display:inline-block;border:1px solid var(--line);padding:3px 10px;border-radius:20px;font-size:12px;color:var(--muted);background:#fff}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:26px 0}
input[type=search]{font:inherit;padding:12px 16px;border:1px solid #b5c5c9;border-radius:8px;background:white;min-width:280px;flex:1;font-size:15px}
input[type=search]:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(7,103,118,0.15)}
.search-field{flex:1;min-width:min(100%,280px)}
.search-field label{display:block;font-size:14px;font-weight:600;margin-bottom:5px}
.search-field input[type=search]{width:100%;min-width:0}
.limit-field{display:flex;align-items:center;gap:10px;align-self:flex-end;min-height:50px;font-size:14px}
.limit-field select{font:inherit;padding:11px 14px;border:1px solid #b5c5c9;border-radius:8px;background:white;color:var(--ink)}
.search-count{font-size:14px;color:var(--muted);margin:0 0 20px}
.pose-result img{aspect-ratio:1;object-fit:contain}
.pose-result h2{font-size:18px;overflow-wrap:anywhere}
.pose-result .code{font-size:13px;font-weight:700;color:var(--accent);margin-bottom:7px}
.pose-result .body{gap:5px;padding:17px}
.pose-result .links{margin-top:auto}
.button,.download{display:inline-block;text-decoration:none;background:var(--accent);color:white;border-radius:6px;padding:8px 14px;font-weight:600;font-size:14px;transition:background-color .15s}
.button:hover,.download:hover{background:var(--accent-hover);color:white}
.download{padding:4px 11px;background:#e8f1f2;color:#145562;font-size:12px}
.group{margin:30px 0 42px;background:white;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.sheet{display:block;width:100%;height:auto}
.rows{padding:6px 20px}
.row{display:grid;grid-template-columns:minmax(230px,1fr) auto;align-items:center;gap:15px;padding:15px 0;border-top:1px solid var(--line)}
.row:first-child{border:0}
.row small{font-size:12px;color:var(--muted)}
.links{display:flex;gap:6px;flex-wrap:wrap}
.note{background:#e8f2f1;border-left:4px solid #076776;padding:14px 20px;margin:24px 0;border-radius:0 8px 8px 0;font-size:14px;line-height:1.7}
.prose{max-width:860px;background:white;border:1px solid var(--line);border-radius:12px;padding:30px;margin:24px 0}
.prose h2{margin-top:0}
.prose h3{margin-top:20px}
.prose li{margin:8px 0}
code{font-size:13px;font-family:Consolas,Menlo,Monaco,monospace;background:#ebf0f1;padding:2px 5px;border-radius:4px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#eef2f3;border-radius:8px;font-size:13px;font-family:Consolas,Menlo,Monaco,monospace}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f8faf9;font-weight:700}
footer{max-width:1200px;padding:28px 24px;margin:auto;font-size:13px;color:var(--muted);border-top:1px solid var(--line);text-align:center}
[hidden]{display:none!important}
.planned{padding:30px;min-height:180px;display:flex;flex-direction:column;justify-content:center}
.back{font-size:14px;text-decoration:none;display:inline-block;margin-bottom:8px}
.bulk{margin-top:40px}
.empty{color:var(--muted);padding:30px}
.chip{padding:6px 13px;border:1px solid var(--line);border-radius:20px;text-decoration:none;font-size:13px;background:white;transition:all .15s}
.chip:hover{border-color:var(--accent);color:var(--accent);background:#f2f7f8}
.faq{margin:54px 0 36px;max-width:960px}
.faq h2{font-size:26px;letter-spacing:-.02em;margin-bottom:8px}
.faq-intro{color:var(--muted);font-size:15px;margin-bottom:24px}
.faq-list{display:flex;flex-direction:column;gap:14px}
.faq-item{background:white;border:1px solid var(--line);border-radius:12px;padding:18px 22px;transition:border-color .2s,box-shadow .2s}
.faq-item:hover{border-color:#b0c2c6;box-shadow:0 3px 10px rgba(0,0,0,0.03)}
.faq-item summary{font-weight:700;font-size:16px;cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:space-between;gap:16px;color:var(--ink);user-select:none}
.faq-item summary::-webkit-details-marker{display:none}
.faq-item summary::after{content:'+';font-size:22px;line-height:1;font-weight:400;color:var(--accent);flex-shrink:0;transition:transform .2s}
.faq-item[open] summary::after{content:'−'}
.faq-item[open] summary{color:var(--accent);margin-bottom:14px}
.faq-ans{font-size:15px;line-height:1.8;color:#2c3c44;border-top:1px solid var(--line);padding-top:14px}
.faq-ans p{margin:8px 0}
.faq-ans ul,.faq-ans ol{margin:8px 0;padding-left:22px}
.faq-ans li{margin:6px 0}
.faq-q-badge{display:inline-block;background:#e3f1f3;color:#0e5866;font-size:12px;font-weight:700;padding:2px 7px;border-radius:4px;margin-right:8px}
.bulk-box{background:white;border:1px solid var(--line);border-radius:14px;padding:26px 28px;margin:36px 0}
.bulk-box h2{margin-top:0}
@media(max-width:850px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.row{grid-template-columns:1fr;gap:8px}main{padding:28px 16px}nav{padding:15px 16px;gap:14px}.rows{padding:5px 14px}}
@media(max-width:520px){.cards{grid-template-columns:1fr}.stats{gap:20px}nav a{font-size:13px}.brand{width:100%}.prose{padding:20px}td,th{padding:10px 8px}}
body[data-package-format="bvh"] [data-format="blend"],body[data-package-format="blend"] [data-format="bvh"],body[data-package-format] .bulk-downloads{display:none!important}
'''


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def esc(value):return html.escape(str(value),quote=True)
def mib(size):return f'{size/1048576:.1f} MB'
def link(url,label,download=False,asset_format=None):
    return f'<a class="download" href="{esc(url)}"'+(' download' if download else '')+(f' data-format="{esc(asset_format)}"' if asset_format else '')+f'>{esc(label)}</a>'


def page(title,body,is_top=False):
    faq_link = '#faq' if is_top else 'index.html#faq'
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | PoseLoom</title><link rel="stylesheet" href="site.css"></head><body><header><nav><a class="brand" href="index.html">PoseLoom / POSE LIBRARY</a><a href="search.html">ポーズ検索</a><a href="howto.html">使い方</a><a href="{faq_link}">よくある質問（FAQ）</a><a href="licenses.html">利用規約・出所</a></nav></header><main>{body}</main><footer>PoseLoom · 3Dポーズ素材ライブラリ（BVH / Blender Blend） · 人体データ出所: Meta Momentum Human Rig (MHR)</footer></body></html>'''


def code_order(row):
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)',row['id']))


def search_page(rows,collections,packaged=False):
    names={c['id']:c['name'] for c in collections}
    title='収録ポーズ検索' if packaged else '全ポーズ検索'
    scope='このZIPに収録されたポーズ' if packaged else 'すべてのコレクションのポーズ'
    body=f'''<a class="back" href="index.html">← カタログ一覧へ戻る</a><p class="eyebrow">POSE SEARCH</p>
<h1>{title}</h1><p class="lead">{scope}を、コード・ポーズ名・カテゴリで検索できます。スペースで区切ると、すべての語を含むポーズに絞り込みます。結果はコード順に、指定した件数まで表示します。</p>
<div class="toolbar search-toolbar" role="search" aria-label="ポーズ検索">
<div class="search-field"><label for="pose-search">キーワード・コード</label><input id="pose-search" type="search" placeholder="例：F001、寝そべる、ソファ 肩" autocomplete="off" aria-controls="search-results"></div>
<label class="limit-field" for="result-limit">表示件数<select id="result-limit" aria-controls="search-results"><option value="50" selected>50件</option><option value="100">100件</option><option value="200">200件</option></select></label>
</div><p id="search-count" class="search-count" role="status" aria-live="polite"></p>
<p id="search-empty" class="empty" hidden>条件に一致するポーズはありません。別のキーワードでお試しください。</p>
<noscript><p class="note">検索にはJavaScriptを有効にしてください。<a href="index.html">コレクション一覧</a>からも閲覧できます。</p></noscript>
<div class="cards" id="search-results">'''
    for row in sorted(rows,key=code_order):
        collection=names[row['collection']]
        keywords=' '.join([row['id'],row['name_ja'],row['category'],collection])
        links=[]
        for key,label in [('bvh','BVH'),('bvh_person_1','BVH 人物1'),('bvh_person_2','BVH 人物2'),('blend','Blend')]:
            if key in row['files']:links.append(link(row['files'][key],label,True,Path(row['files'][key]).suffix[1:]))
        body+=f'''<article class="card pose-result" data-id="{esc(row['id'])}" data-search="{esc(keywords)}" hidden><img src="{esc(row['files']['preview'])}" loading="lazy" width="1024" height="1024" alt="{esc(row['id']+' '+row['name_ja'])}"><div class="body"><span class="code">{esc(row['id'])}</span><h2>{esc(row['name_ja'])}</h2><p><a href="collection-{esc(row['collection'])}.html#{esc(row['id'])}">{esc(collection)}</a> · {esc(row['category'])}</p><div class="links">{''.join(links)}</div></div></article>'''
    body+=r'''</div><script>
(() => {
  const query = document.querySelector('#pose-search');
  const limit = document.querySelector('#result-limit');
  const normalize = value => value.normalize('NFKC').toLowerCase();
  const cards = [...document.querySelectorAll('.pose-result')].map(card => ({card, text: normalize(card.dataset.search)}));
  function update() {
    const words = normalize(query.value).trim().split(/\s+/u).filter(Boolean);
    const cap = [50, 100, 200].includes(Number(limit.value)) ? Number(limit.value) : 50;
    let matched = 0;
    let shown = 0;
    for (const {card, text} of cards) {
      const matches = words.every(word => text.includes(word));
      card.hidden = !matches || shown >= cap;
      if (matches) matched++;
      if (!card.hidden) shown++;
    }
    document.querySelector('#search-count').textContent = `${cards.length}件中 ${matched}件が一致・${shown}件を表示（コード順）` + (matched > cap ? '。表示件数を増やすか、キーワードで絞り込んでください。' : '。');
    document.querySelector('#search-empty').hidden = matched !== 0;
  }
  limit.value = '50';
  query.addEventListener('input', update);
  limit.addEventListener('change', update);
  update();
})();
</script>'''
    return page(title,body)


def font(size):
    from PIL import ImageFont
    for p in ['C:/Windows/Fonts/YuGothM.ttc','C:/Windows/Fonts/meiryo.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']:
        if Path(p).is_file():return ImageFont.truetype(p,size)
    return ImageFont.load_default(size=size)


def sheets(site,collection,rows):
    from PIL import Image,ImageDraw,ImageOps
    result=[];folder=site/'sheets'/collection['id'];folder.mkdir(parents=True,exist_ok=True)
    for start in range(0,len(rows),6):
        chunk=rows[start:start+6];canvas=Image.new('RGB',(1200,1160),'#f1f3f5');draw=ImageDraw.Draw(canvas)
        number=start//6+1
        draw.text((18,10),f"{collection['name']} / {number:02}",font=font(23),fill='#20313c')
        for n,row in enumerate(chunk):
            x=(n%3)*400;y=48+(n//3)*552
            with Image.open(site/row['files']['preview']) as im:picture=ImageOps.contain(im.convert('RGB'),(388,488))
            canvas.paste(picture,(x+(400-picture.width)//2,y+(488-picture.height)//2))
            label=f"{row['id']}  {row['name_ja']}"
            fs=20
            while draw.textlength(label,font=font(fs))>382 and fs>12:fs-=1
            draw.text((x+10,y+493),label,font=font(fs),fill='#182b38')
            draw.text((x+10,y+520),row['category'],font=font(16),fill='#596879')
        name=f'sheets/{collection["id"]}/contact_{number:02}.jpg';canvas.save(site/name,quality=90)
        result.append({'file':name,'ids':[r['id'] for r in chunk]})
    return result


def download_button(key,urls):
    if urls.get(key):raise ValueError('Use separate download URL keys: '+key+'-bvh and '+key+'-blend')
    buttons=[]
    for fmt,label in [('bvh','BVH'),('blend','Blend')]:
        url=urls.get(key+'-'+fmt)
        if url:
            parsed=urllib.parse.urlparse(url)
            if parsed.scheme!='https' or not parsed.netloc:raise ValueError('Download URL must be HTTPS: '+key+'-'+fmt)
            buttons.append(f'<a class="button" data-format="{fmt}" href="{esc(url)}" rel="noopener">{label} 一括ZIP</a>')
        else:buttons.append(f'<span class="status" data-format="{fmt}">{label} ZIPの公開URLは準備中</span>')
    return '<div class="bulk-downloads">'+' '.join(buttons)+'</div>'


def package_html(content,fmt):
    """Reuse the public catalog, hiding and disabling unavailable downloads."""
    if fmt not in ('bvh','blend'):raise ValueError('Unknown ZIP format: '+fmt)
    label='BVH' if fmt=='bvh' else 'Blend'
    content=content.replace('<body>',f'<body data-package-format="{fmt}">',1)
    content=content.replace('<main>',f'<main><p class="note">【{label}版パッケージ】このZIPには、{label}形式のポーズデータ、オフライン用カタログ、プレビュー画像、利用規約文書を収録しています。</p>',1)
    def disable(match):
        tag=match.group()
        attribute=re.search(r' data-format="([^"]+)"',tag)
        if attribute and attribute.group(1)!=fmt:
            tag=re.sub(r' href="[^"]*"| download(?:="[^"]*")?', '',tag)
            tag=tag[:-1]+' hidden aria-hidden="true">'
        return tag
    return re.sub(r'<a\b[^>]*>',disable,content)


def faq_section():
    faqs = [
        (
            'ダウンロードできるファイルの種類（BVHとBlend）はどう使い分ければいいですか？',
            '''<p>用途やお使いの制作ソフトに合わせて、以下の通り使い分けていただけます。</p>
<ul>
  <li><strong>BVH形式</strong>：<strong>CLIP STUDIO PAINT（クリスタ）</strong>などの3Dデッサン人形にポーズを読み込ませたい場合に最適です。ボーンの回転データのみが記録された軽量なファイルで、ドラッグ＆ドロップするだけで素早くポーズを適用できます。</li>
  <li><strong>Blend形式</strong>：3D制作ソフト<strong>「Blender」</strong>専用のプロジェクトファイルです。人体3Dモデル、ボーン構造、操作用のIK（インバースキネマティクス）コントローラーが設定されており、手足や視線を微調整したり、カメラアングルを変えてレンダリングしたり、自作モデルへポーズを移植したい場合に適しています。</li>
</ul>'''
        ),
        (
            'どのような用途に使えますか？ 商用利用やクレジット表記は必要ですか？',
            '''<p><strong>商用・非商用を問わず、イラスト、マンガ、Webtoon、同人誌、アニメーション、ゲーム、Webサイト、映像制作などの創作活動に自由にご利用いただけます。</strong></p>
<p>本素材をもとに制作したイラストや成果物について、<strong>「PoseLoomを使用した」等のクレジット表記や利用報告は一切不要</strong>です（クレジットを掲載していただける場合は歓迎いたします）。また、成人向け表現（R-18）を含む作品での利用も問題ありません。</p>
<p>※なお、本3D素材データそのものを再配布・転売・改変配布する場合は、ベース骨格のライセンス（Apache License 2.0）に基づく遵守事項（ライセンス全文や著作権表示の保持など）が必要となります。詳しくは<a href="licenses.html">利用規約・出所</a>ページをご確認ください。</p>'''
        ),
        (
            '目的のポーズを効率よく探すにはどうすればよいですか？',
            '''<p>以下の方法でお探しいただけます。</p>
<ol>
  <li><strong>全ポーズ検索</strong>：<a href="search.html">ポーズ検索画面</a>では、コード・ポーズ名・カテゴリで検索できます。コード順に初期50件を表示し、50・100・200件に切り替えられます。ZIP内では、そのZIPに収録した素材を検索できます。</li>
  <li><strong>テーマ別コレクション</strong>：トップページから「日常・動作」「バスケットボール」「寝姿・床ヨガ」などのカテゴリを選んでアクセスしてください。</li>
  <li><strong>一覧コンタクトシート</strong>：各コレクションページでは、6ポーズずつまとめた一覧プレビュー画像を掲載しており、全体のポーズやバリエーションを一目で俯瞰できます。</li>
  <li><strong>リアルタイム検索</strong>：コレクションページ上部にある検索窓に、キーワード（例：「走る」「シュート」「座る」「腕」など）やポーズIDを入力すると、該当するポーズだけを瞬時に絞り込むことができます。</li>
</ol>'''
        ),
        (
            '複数のポーズをまとめてダウンロードしたい場合はどうすればよいですか？',
            '''<p>各コレクションページの上部に<strong>「テーマ別 一括ZIP（BVH版 / Blend版）」</strong>をご用意しています。</p>
<p>素材を1点ずつ個別にダウンロードするよりも、一括ZIPをご利用いただくことでスムーズかつまとめてダウンロードいただけます。展開したフォルダ内には、オフライン環境でもポーズの検索・閲覧ができる専用のHTMLカタログが同梱されています。</p>'''
        ),
        (
            'CLIP STUDIO PAINT（クリスタ）への読み込み手順を教えてください。',
            '''<p>以下の簡単なステップでデッサン人形へポーズを適用できます。</p>
<ol>
  <li>クリスタのキャンバス上に、素材パレットからお好みの「3Dデッサン人形」をドラッグ＆ドロップして配置します。</li>
  <li>ダウンロードした <code>.bvh</code> ファイルを、キャンバス上のデッサン人形へ直接ドラッグ＆ドロップします（またはメニューの［ファイル］→［読み込み］→［3Dデータ］からBVHを選択）。</li>
  <li>1フレーム目のポーズが人形に反映されます。人形の頭身や体型に合わせて手足の接地や角度を微調整してください。［ポーズ素材として登録］を行っておくと次回以降も手軽に呼び出せます。</li>
</ol>
<p>※二人の配置（ペア素材）の場合は、人物別に分かれたBVHファイル（人物1 / 人物2）をそれぞれのデッサン人形へ適用してください。</p>'''
        ),
        (
            'Blenderで編集する際、特別なプラグインやアドオンは必要ですか？',
            '''<p>いいえ、有料プラグインや外部アドオンのインストールは一切不要です。標準のBlender（Blender 4.0以降推奨）だけでそのまま開いて編集できます。</p>
<p>手足や頭部には標準的なIKコントローラー（CTRLボーン）があらかじめ設定されているため、コントローラーを移動・回転させるだけで直感的にポーズの微調整が可能です。</p>'''
        ),
        (
            '二人ポーズ（ペア）や背景付きの素材はどう使えばよいですか？',
            '''<p>二人ポーズのBVHファイルは人物ごとに分かれて収録（<code>person_1.bvh</code> / <code>person_2.bvh</code>）されています。クリスタ等のデッサン人形へそれぞれ個別にポーズを適用してください。</p>
<p>2人の正確な位置関係や距離感、カメラアングルをそのまま使いたい場合は、Blendファイルを開いていただくのが最も便利です。</p>'''
        ),
        (
            '3D素材データそのものを再配布・二次配布することはできますか？',
            '''<p>本素材の人体3Dメッシュおよび基本骨格は、Meta社が公開しているオープンソースリグ「Momentum Human Rig (MHR)」に基づいており、<strong>Apache License 2.0</strong> が適用されます。</p>
<p>Apache 2.0 の条件に従い、元の著作権表示（Copyright (c) Meta Platforms, Inc. and affiliates）、ライセンス全文、NOTICEファイル、および改変内容の明記を保持した上での再配布・改変は認められています。ただし、本素材をそのまま無断で自身の著作物と偽って配布・販売する行為や、ライセンス表示を削除しての再配布は禁止されています。</p>'''
        )
    ]
    items = []
    for q, a in faqs:
        items.append(f'<details class="faq-item"><summary><span><span class="faq-q-badge">Q</span>{esc(q)}</span></summary><div class="faq-ans">{a}</div></details>')
    return f'''<section class="faq" id="faq">
<h2>よくある質問（FAQ）</h2>
<p class="faq-intro">素材の利用方法、形式の違い、ライセンスについて寄せられる代表的なご質問をまとめています。</p>
<div class="faq-list">
{''.join(items)}
</div>
</section>'''


def howto():
    return page('使い方ガイド','''<span class="eyebrow">GET STARTED</span><h1>制作環境に合わせて、形式を選んで使う。</h1>
<div class="prose">
<h2>CLIP STUDIO PAINT（クリスタ）で3Dデッサン人形にポーズを適用する</h2>
<ol>
<li>カタログから使いたいポーズの <strong>BVH</strong> ファイルをダウンロードします。</li>
<li>CLIP STUDIO PAINTのキャンバス上に、素材パレットから3Dデッサン人形を配置します。</li>
<li>ダウンロードした <code>.bvh</code> ファイルをキャンバス上のデッサン人形へ直接ドラッグ＆ドロップします（またはメニューの［ファイル］→［読み込み］→［3Dデータ］からBVHを選択）。</li>
<li>1フレーム目のポーズがデッサン人形へ即座に反映されます。人形の頭身やキャラクターの体型に合わせて手足の接地や関節角度を微調整し、必要に応じて［ポーズ素材として登録］を行っておくと便利です。</li>
</ol>
<p>※二人組のポーズ素材は、人物別に分かれたBVH（人物1 / 人物2）をそれぞれのデッサン人形へ個別に適用してください。2人の位置関係やカメラアングルはBlendファイル側に保存されています。</p>
<p>※本ライブラリのBVHは、中立骨格からの回転情報を含む1フレームの静止ポーズデータです。Blender等での再読み込み検証を行っています。</p>
<p><a href="https://help.clip-studio.com/ja-jp/manual_jp/660_3d/3D%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB%E3%82%92%E8%AA%AD%E3%81%BF%E8%BE%BC%E3%82%80.htm" target="_blank" rel="noopener">CLIP STUDIO PAINT公式マニュアル：3Dファイルを読み込む</a></p>
</div>

<div class="prose">
<h2>Blenderで編集・レンダリングする</h2>
<p>ダウンロードした <code>.blend</code> ファイルをBlender（Blender 4.0以降推奨）で直接開きます。専用のアドオンやプラグインのインストールは不要です。</p>
<p>手足や頭部、腰に配置されたIKコントローラー（CTRLボーン）をギズモで移動・回転させることで、直感的にポーズの微調整が行えます。膝や肘の向きはポールターゲットで簡単に制御できます。</p>
<p>男女の基本モデルには、標準体型やアニメ体型など複数の体形プリセットがあらかじめ組み込まれています。編集した後は、作業用の新しいファイル名で保存してご利用ください。</p>
</div>

<div class="prose">
<h2>3D制作ツールやスクリプトから活用する（上級者向け）</h2>
<p>必要なメタデータはすべてBlendファイル内にテキストデータとして埋め込まれており、外部のJSONファイルを用意することなくPythonスクリプト等から直接読み出せます。</p>
<p>Blenderのテキストエディターから <code>asset.json</code>（素材情報・カテゴリ・制作者情報）や <code>rig.json</code>（ボーン構造・静止時と保存姿勢の変換行列・カメラ座標）を確認できます。</p>
<pre>import bpy, json
asset = json.loads(bpy.data.texts["asset.json"].as_string())
rig = json.loads(bpy.data.texts["rig.json"].as_string())</pre>
<p><strong>座標系と単位</strong>：Blendファイルは メートル（m）・Z軸上・前方-Y、BVHファイルは センチメートル（cm）・Y軸上 で出力されています。標準的なBlenderアーマチュアとメッシュ構造を採用しているため、他形式へのコンバートや自作リグへのリターゲットもスムーズに行えます。</p>
</div>

<div class="prose">
<h2>配布内容と仕様</h2>
<p>本ライブラリの素材は <strong>BVH</strong> と <strong>Blend</strong> の2つの形式で提供しています。単体ポーズは両形式、背景のみのシーン素材はBlend形式、二人ポーズは人物別BVHと統合Blend形式となっています。プレビュー画像、HTMLカタログ、および利用規約文書を添えて配布しています。</p>
</div>''')


def license_page():
    return page('素材の利用条件・ライセンス・出所','''<span class="eyebrow">TERMS & LICENSES</span><h1>素材の利用条件・ライセンス・出所</h1>

<div class="prose">
<h2>1. 成果物での利用について（商用・非商用フリー、クレジット表記不要）</h2>
<p>本ライブラリのポーズ素材は、イラストレーター、漫画家、アニメーター、3Dクリエイターの創作活動を幅広く支援することを目的としています。</p>
<p>本素材をポーズの参考、デッサンのアタリ、作画の下絵、あるいは3Dシーンの配置素材として使用して制作された<strong>イラスト、マンガ、同人誌、アニメーション、ゲーム、映像、Webコンテンツ等の成果物は、商用・非商用を問わず自由にご利用・公開・販売いただけます。</strong></p>
<p>成果物の発表にあたり、<strong>「PoseLoomを使用した」等のクレジット表記や事前の利用報告は一切不要</strong>です（表記していただける場合は歓迎いたします）。また、成人向け作品（同人誌・商業誌を問わず）でのご利用にも制限はありません。</p>
</div>

<div class="prose">
<h2>2. 人体メッシュ・骨格の出所とベースライセンス（Apache License 2.0）</h2>
<p>本素材の人体3Dメッシュおよび基本骨格構造は、Meta社が公開しているオープンソースの人物リグ <strong>「Momentum Human Rig (MHR)」</strong> に由来しています。Copyright (c) Meta Platforms, Inc. and affiliates.</p>
<p>MHRは <strong>Apache License 2.0</strong> の下で公開されており、利用・改変・商用利用・再配布が許諾されています。</p>
<p>PoseLoomでは、MHRのメッシュ・ボーン構造をもとに、イラスト・マンガ制作に適した体形調整（プロポーション最適化）、Blender用IKコントローラーの構築、マテリアル・服色の設定、各種ポーズの推定および手作業による調整、ファイル形式の変換（BVH / Blend）を行いました。</p>
<p>※本ライブラリは有志による独自の制作物であり、Meta社による公式素材や推奨を意味するものではありません。</p>
<p><a href="licenses/sam3dbody/LICENSE-MHR" target="_blank">Apache License 2.0 全文</a> · <a href="licenses/sam3dbody/NOTICE-MHR" target="_blank">MHR NOTICE</a> · <a href="https://github.com/facebookresearch/MHR/blob/main/LICENSE" target="_blank" rel="noopener">MHR 公式リポジトリライセンス</a></p>
</div>

<div class="prose">
<h2>3. 3Dデータそのものの再配布・改変に関する規約</h2>
<p>成果物（イラストや画像など）の利用とは異なり、<strong>本ライブラリの3Dデータ（BlendファイルやBVHファイル）そのものを再配布、転載、または改変して再配布する場合</strong>は、上流ライセンスである <strong>Apache License 2.0</strong> の条項を遵守する必要があります。</p>
<p>再配布を行う際は、以下の条件を遵守してください：</p>
<ul>
  <li>Apache License 2.0 のライセンス全文（LICENSE-MHR）を同梱すること</li>
  <li>Meta社の著作権表示およびNOTICE（NOTICE-MHR）を保持すること</li>
  <li>元のデータに改変を加えた場合は、改変を行った旨の通知（変更通知）を明記すること</li>
</ul>
<p><strong>【禁止事項】</strong></p>
<ul>
  <li>本3D素材データそのものを、無断で自身の著作物と偽って配布・販売する行為</li>
  <li>元の著作権表示やライセンス文書を削除した状態で3D素材データを再配布する行為</li>
</ul>
</div>

<div class="prose">
<h2>4. 制作に使用したソフトウェア・AI技術について</h2>
<p>本素材の制作パイプラインにおける姿勢推定処理には、Meta SAM 3D Body（SAM License）および ComfyUI-SAM3DBody_utills（MIT License）を活用しています。</p>
<p>本素材パッケージには、<strong>AI推論モデルの重み（ウェイト）やSAMプログラム本体は一切含まれていません</strong>。推定および調整を経て生成された3Dポーズデータ（ポリゴンメッシュおよびボーン座標データ）のみを収録しています。</p>
<p>また、本データは3Dソフトウェア「Blender」を用いて作成・出力されていますが、Blender財団の公式見解に基づき、Blenderで作成・出力されたデータであることのみを理由として3Dデータ自体がGPLライセンスに拘束されることはありません（<a href="https://www.blender.org/about/license/" target="_blank" rel="noopener">Blender公式のライセンス説明</a>を参照）。</p>
<p><a href="licenses/sam3dbody/LICENSE" target="_blank">構成別ライセンス一覧</a> · <a href="licenses/sam3dbody/LICENSE-MIT" target="_blank">MIT License 全文</a> · <a href="licenses/sam3dbody/LICENSE-SAM" target="_blank">SAM License 全文</a> · <a href="licenses/sam3dbody/THIRD_PARTY_NOTICES" target="_blank">第三者通知</a></p>
</div>

<div class="prose">
<h2>5. 免責事項</h2>
<p>本素材は現状有姿（AS IS）で提供されます。本素材の利用、改変、ダウンロード等によって利用者に生じたいかなる直接的・間接的トラブルや損害についても、制作元および権利者は一切の責任を負いかねます。各自の責任と判断においてご利用ください。</p>
</div>''')


def build(plan_path,out,urls,records):
    plan=read(plan_path);root=plan_path.parent;site=out;site.mkdir(parents=True,exist_ok=False)
    ids=[a['id'] for a in plan['assets']]
    groups=[c['id'] for c in plan['collections']]
    if len(ids)!=len(set(ids)) or len(groups)!=len(set(groups)):
        raise ValueError('Asset and collection IDs must be unique')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in ids+groups):
        raise ValueError('Use letters, numbers, underscore or hyphen for IDs')
    if any(a['collection'] not in groups for a in plan['assets']):
        raise ValueError('Unknown collection')
    shutil.copytree(root/plan['license_source'],site/'licenses',dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.json'))
    (site/'site.css').write_text(CSS,encoding='utf-8')
    (site/'howto.html').write_text(howto(),encoding='utf-8')
    (site/'licenses.html').write_text(license_page(),encoding='utf-8')
    items=[]
    export_root=(root/plan['export_root']).resolve()
    for a in plan['assets']:
        cache=export_root/a['collection']/a['id']
        folder=site/'assets'/a['collection']/a['id']
        if not (cache/'export.json').is_file():raise FileNotFoundError(f'Export is not complete: {a["id"]}')
        export=read(cache/'export.json');rig=read(cache/'rig.json');entry=read(cache/'asset.json')
        if export['stamp']['source_sha256']!=sha(root/a['source']):raise ValueError('Changed source: '+a['id'])
        for n,h in export['sha256'].items():
            if sha(cache/n)!=h:raise ValueError('Changed export: '+str(cache/n))
        folder.mkdir(parents=True,exist_ok=True)
        public_metadata={}
        for n in rig['files'].values():
            if Path(n).suffix not in ('.blend','.bvh') or Path(n).name!=n:
                raise ValueError('Only BVH/blend assets are distributed: '+n)
            cleaned=clean_file(cache/n,folder/n)
            public_metadata.update(cleaned['metadata'])
        preview=site/'previews'/a['collection']/(a['id']+'.png');preview.parent.mkdir(parents=True,exist_ok=True)
        clean_file(root/a['preview'],preview)
        if not {'asset.json','rig.json'}<=public_metadata.keys():
            raise ValueError('Missing embedded public metadata: '+a['id'])
        for name,value in public_metadata.items():
            privacy_json(records/'public_metadata'/a['collection']/a['id']/name,clean_json(value))
        rel=folder.relative_to(site).as_posix()
        public={k:a[k] for k in ['id','name_ja','category','collection','kind','visual_review']}
        public.update(files={**{k:f'{rel}/{v}' for k,v in rig['files'].items()},'preview':preview.relative_to(site).as_posix()},
                      embedded_metadata={'asset':'asset.json','rig':'rig.json'},source_blend_sha256=rig['source_sha256'])
        public['sha256']={k:sha(site/v) for k,v in public['files'].items()}
        items.append(public)
    collections=[]
    for c in plan['collections']:
        rows=[r for r in items if r['collection']==c['id']]
        c={**c,'count':len(rows),'page':f'collection-{c["id"]}.html','sheets':sheets(site,c,rows)}
        collections.append(c)
        intro=f'<a class="back" href="index.html">← カタログ一覧へ戻る</a><p class="eyebrow">POSE COLLECTION</p><h1>{esc(c["name"])}</h1><p class="lead">{esc(c["description"])}</p>'
        intro+=f'<div class="toolbar"><strong>{len(rows)} 素材</strong>{download_button(c["id"],urls)}</div>'
        if c['status']=='partial':intro+=f'<p class="note">※本コレクションは制作進行中です。目標{c["target"]}件のうち、完成した{len(rows)}件を先行収録しています。</p>'
        intro+='<div class="toolbar"><input id="search" type="search" placeholder="キーワード・ポーズ名・IDで検索（例: 走る, 01）" aria-label="ポーズ検索"><span id="hits" aria-live="polite"></span></div>'
        groups=[]
        for sheet in c['sheets']:
            chunk=[r for r in rows if r['id'] in sheet['ids']]
            search=' '.join(r['id']+' '+r['name_ja']+' '+r['category'] for r in chunk)
            block=f'<section class="group" data-search="{esc(search.lower())}"><img class="sheet" src="{esc(sheet["file"])}" loading="lazy" width="1200" height="1160" alt="{esc("、".join(r["id"]+" "+r["name_ja"] for r in chunk))}"><div class="rows">'
            for r in chunk:
                links=[]
                for key,label in [('bvh','BVH'),('bvh_person_1','BVH 人物1'),('bvh_person_2','BVH 人物2'),('blend','Blend')]:
                    if key in r['files']:links.append(link(r['files'][key],label,True,Path(r['files'][key]).suffix[1:]))
                block+=f'<div class="row" id="{esc(r["id"])}"><div><h3>{esc(r["name_ja"])}</h3><small>{esc(r["id"])} · {esc(r["category"])}</small></div><div class="links">{"".join(links)}</div></div>'
            groups.append(block+'</div></section>')
        if not rows:groups.append('<p class="empty">制作原稿を準備済みです。素材の完成後に順次追加されます。</p>')
        js='''<script>const search=document.querySelector('#search');const groups=[...document.querySelectorAll('.group')];search.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();let n=0;for(const g of groups){g.hidden=!g.dataset.search.includes(q);if(!g.hidden)n++;}document.querySelector('#hits').textContent=q?`${n} 件のポーズが一致`:'';});</script>'''
        (site/c['page']).write_text(page(c['name'],intro+''.join(groups)+js),encoding='utf-8')
    catalog={'schema_version':1,'title':plan['title'],'path_base':'catalog directory',
        'license_status':'upstream_confirmed_local_draft','collections':collections,'assets':items}
    write(records/'catalog.json',catalog)
    write(records/'downloads.json',{'schema_version':1,'urls':urls,'note':'Local build record. Null means unpublished.'})
    (site/'search.html').write_text(search_page(items,collections),encoding='utf-8')
    hero=f'''<p class="eyebrow">POSES FOR DRAWING & CREATION</p>
<h1>描きたいポーズを、<br>そのまま使える3Dデータに。</h1>
<p class="lead">イラスト、マンガ、アニメーション、3D制作のためのポーズデータ集です。CLIP STUDIO PAINTの3Dデッサン人形に直接読み込めるBVHファイルと、Blenderでボーンや体形を自由に編集できるBlendファイルを全ポーズ無料・登録不要で提供しています。</p>
<div class="stats">
<div class="stat"><strong>{len(items)}</strong><span>収録ポーズ数</span></div>
<div class="stat"><strong>{sum(bool(c["count"]) for c in collections)}</strong><span>公開中コレクション</span></div>
<div class="stat"><strong>6</strong><span>一覧画像あたりのポーズ数</span></div>
</div>'''
    hero+='<p><a class="button" href="search.html">全ポーズから検索する</a></p><div class="toolbar">'+''.join(f'<a class="chip" href="{c["page"]}">{esc(c["name"])}</a>' for c in collections)+'</div><div class="cards">'
    for c in collections:
        if c['sheets']:
            hero+=f'<a class="card" href="{c["page"]}"><img src="{c["sheets"][0]["file"]}" loading="lazy" width="1200" height="1160" alt="{esc(c["name"])}のプレビュー"><div class="body"><span class="count">{c["count"]}</span><h2>{esc(c["name"])}</h2><p>{esc(c["description"])}</p><span class="status">{("追加予定あり" if c["status"]=="partial" else "ダウンロード")}</span></div></a>'
        else:hero+=f'<a class="card planned" href="{c["page"]}"><span class="status">今後追加</span><h2>{esc(c["name"])}</h2><p>{esc(c["description"])}</p></a>'
    hero+='''</div>
<div class="bulk-box">
<h2>テーマ別の一括ダウンロード</h2>
<p>各コレクションのページ上部から、カテゴリごとの全ポーズをまとめた「テーマ別一括ZIP（BVH版 / Blend版）」をダウンロードいただけます。複数のポーズをまとめて利用したい場合や、オフライン環境でカタログを閲覧したい場合にご活用ください。</p>
</div>'''
    hero+=faq_section()
    hero+='<p class="note">※プレビュー画像はBlenderで撮影したレンダリング画像です。商用・非商用問わず漫画やイラスト等の創作でご自由にお使いいただけます。詳しくは<a href="licenses.html">利用規約・出所</a>および<a href="howto.html">使い方ガイド</a>をご確認ください。</p>'
    (site/'index.html').write_text(page('ポーズカタログ',hero,is_top=True),encoding='utf-8')
    return catalog


def public_metadata(value):
    value=clean_json(value)
    license=value.get('license')
    suffix=' proportions, IK, materials, pose transfer, scene and export'
    if isinstance(license,dict) and isinstance(license.get('modifications'),str):
        if license['modifications'].endswith(suffix):
            license['modifications']='PoseLoom'+suffix
    if isinstance(license,dict) and isinstance(license.get('origin'),str):
        if license['origin'].endswith(' primitive scene'):
            license['origin']='PoseLoom primitive scene'
    return value


def verify_zip_metadata(path):
    with zipfile.ZipFile(path) as archive:
        names=set(archive.namelist())
        catalog=json.loads(archive.read('catalog.json'))
        for row in catalog['assets']:
            for key,rel in row['files'].items():
                if rel not in names:raise RuntimeError('ZIP catalog file missing: '+rel)
                if key in row.get('sha256',{}) and hashlib.sha256(archive.read(rel)).hexdigest()!=row['sha256'][key]:
                    raise RuntimeError('ZIP catalog hash mismatch: '+rel)
            for rel in row['metadata'].values():
                value=json.loads(archive.read(rel))
                for target in value.get('files',{}).values():
                    if target not in names:raise RuntimeError('ZIP metadata file missing: '+target)
                notice=value.get('license',{}).get('notice')
                if notice and notice not in names:raise RuntimeError('ZIP license notice missing: '+notice)


def make_zips(plan_path,out,catalog,release_dir,records):
    site=out;dest=release_dir;dest.mkdir(parents=True,exist_ok=False);manifest=[]
    common=['site.css','howto.html','licenses.html']
    licenses=[p.relative_to(site).as_posix() for p in (site/'licenses').rglob('*') if p.is_file()]
    def pack(group,fmt,files,extra=None):
        name=group+'-'+fmt
        files=[rel for rel in files if Path(rel).suffix not in ('.bvh','.blend') or Path(rel).suffix=='.'+fmt]
        path=dest/f'poseloom-{name}.zip'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for rel in sorted(set(files)):
                if Path(rel).name=='export.json':continue
                if rel.endswith('.html'):z.writestr(rel,package_html((site/rel).read_text(encoding='utf-8'),fmt))
                else:z.write(site/rel,rel)
            for rel,content in (extra or {}).items():
                z.writestr(rel,package_html(content,fmt) if rel.endswith('.html') else content)
        with zipfile.ZipFile(path) as z:
            broken=z.testzip()
            if broken:raise RuntimeError('ZIP CRC failure: '+broken)
            names=set(z.namelist())
            other='.blend' if fmt=='bvh' else '.bvh'
            if any(n.endswith(other) for n in names):raise RuntimeError('Mixed asset formats: '+name)
            checked_links=0
            for member in names:
                if not member.endswith('.html'):continue
                parsed=Links();parsed.feed(z.read(member).decode('utf-8'))
                for url in parsed.links:
                    u=urllib.parse.urlparse(url)
                    if u.scheme or u.netloc or not u.path:continue
                    target=posixpath.normpath(posixpath.join(posixpath.dirname(member),urllib.parse.unquote(u.path)))
                    if target not in names:raise RuntimeError(f'ZIP link missing: {name}/{member}: {url}')
                    checked_links+=1
        verify_zip_metadata(path)
        manifest.append({'id':name,'collection':group,'format':fmt,'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path),
                         'asset_files':sum(n.endswith('.'+fmt) for n in names),'html_local_links':checked_links,'crc_passed':True})
        print('ZIP',name,mib(path.stat().st_size),flush=True)
    for c in catalog['collections']:
        if not c['count']:continue
        files=common+licenses+[c['page']]+[s['file'] for s in c['sheets']]
        files+=[p.relative_to(site).as_posix() for p in (site/'assets'/c['id']).rglob('*') if p.is_file()]
        files+=[a['files']['preview'] for a in catalog['assets'] if a['collection']==c['id']]
        subset=[a for a in catalog['assets'] if a['collection']==c['id']]
        for fmt in ('bvh','blend'):
            metadata={};public_assets=[]
            for a in subset:
                row=clean_json(a)
                row['files']={k:v for k,v in row['files'].items() if k=='preview' or Path(v).suffix=='.'+fmt}
                row['sha256']={k:v for k,v in row['sha256'].items() if k in row['files']}
                row['metadata']={}
                source=records/'public_metadata'/c['id']/a['id']
                for p in sorted(source.glob('*.json')):
                    value=public_metadata(read(p))
                    value['path_base']='ZIP root'
                    if p.name in ('asset.json','rig.json'):
                        value['files']={k:v for k,v in row['files'].items() if k!='preview'}
                    if isinstance(value.get('license'),dict):value['license']['notice']='licenses.html'
                    rel='metadata/'+c['id']+'/'+a['id']+'/'+p.name
                    metadata[rel]=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
                    row['metadata'][p.stem]=rel
                public_assets.append(row)
            package_catalog={'schema_version':2,'title':catalog['title'],'package_format':fmt,
                'path_base':'ZIP root','collections':[c],'assets':public_assets}
            metadata['catalog.json']=json.dumps(clean_json(package_catalog),ensure_ascii=False,indent=2)+'\n'
            metadata['README.txt']=('PoseLoom offline pose library. Open index.html or search.html.\n'
                'AI/tools: catalog.json lists only included files, previews and metadata.\n'
                'metadata/<collection>/<id>/asset.json: names, provenance and license.\n'
                'rig.json: bones, controls, transforms, units and saved pose.\n'
                'body_preset.json (when present): body proportions.\n'
                'BVH: Y up / centimetres. Blend: Z up / metres.\n'
                'See licenses.html and licenses/; retain upstream notices.\n')
            metadata.update({'index.html':(site/c['page']).read_text(encoding='utf-8'),
                             'search.html':search_page(subset,[c],packaged=True)})
            pack(c['id'],fmt,files,metadata)
    # The producer expects this simple base-model layout after extraction.
    if {'MODEL_MALE','MODEL_FEMALE'} <= {a['id'] for a in catalog['assets']}:
        path=dest/'poseloom-base-models.zip'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            base_assets=[]
            for aid,name in [('MODEL_MALE','male.blend'),('MODEL_FEMALE','female_anime_v2.blend')]:
                z.write(site/'assets/models'/aid/'pose.blend',name)
                row={'id':aid,'files':{'blend':name},'sha256':{'blend':sha(site/'assets/models'/aid/'pose.blend')},'metadata':{}}
                for p in sorted((records/'public_metadata/models'/aid).glob('*.json')):
                    value=public_metadata(read(p))
                    value['path_base']='ZIP root'
                    if p.name in ('asset.json','rig.json'):
                        value['files']={'blend':name}
                    if isinstance(value.get('license'),dict):value['license']['notice']='NOTICE.txt'
                    rel='metadata/'+aid+'/'+p.name
                    z.writestr(rel,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
                    row['metadata'][p.stem]=rel
                base_assets.append(row)
            z.writestr('catalog.json',json.dumps({'schema_version':2,'title':'PoseLoom base models',
                'package_format':'blend','path_base':'ZIP root','assets':base_assets},ensure_ascii=False,indent=2)+'\n')
            for rel in licenses:z.write(site/rel,rel)
            z.writestr('NOTICE.txt','Base models derived from MHR; see licenses/sam3dbody/LICENSE-MHR and NOTICE-MHR. PoseLoom adds IK, proportions and materials.\n')
            z.writestr('SETUP.html','<!doctype html><meta charset="utf-8"><title>Base models</title><h1>基本モデル</h1><p>Blenderでそのまま編集できます。制作ツールを使う場合はassets/modelsへ展開し、kit_config.jsonを設定してから python -X utf8 kit.py prepare-models を実行します。体形プリセットはblend内のbody_preset.jsonに保存されています。</p>')
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
        verify_zip_metadata(path)
        manifest.append({'id':'base-models','collection':'base-models','format':'blend','file':path.name,'bytes':path.stat().st_size,'sha256':sha(path),'asset_files':2,'crc_passed':True})
    write(records/'download_manifest.json',{'archives':manifest})


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        self.links.extend(v for k,v in attrs if k in ('href','src') and v)


def verify(out,records):
    site=out;errors=[];links=0
    for p in out.rglob('*.html'):
        parser=Links();parser.feed(p.read_text(encoding='utf-8'))
        for url in parser.links:
            u=urllib.parse.urlparse(url)
            if u.scheme or u.netloc or not u.path:continue
            links+=1;target=(p.parent/urllib.parse.unquote(u.path)).resolve()
            if not target.is_relative_to(out.resolve()) or not target.is_file():errors.append(f'{p.name}: {url}')
    catalog=read(records/'catalog.json');checked=0
    for a in catalog['assets']:
        for k,h in a['sha256'].items():
            p=site/a['files'][k]
            checked+=1
            if not p.is_file() or sha(p)!=h:errors.append('Hash: '+str(p))
    public=[p for p in site.rglob('*') if p.is_file()]
    oversized=[p.relative_to(site).as_posix() for p in public if p.stat().st_size>25*1024*1024]
    forbidden=[p.relative_to(site).as_posix() for p in public if p.suffix.lower() in {'.md','.log','.blend1','.py','.pyc','.fbx','.json','.zip'}]
    unexpected_assets=[p.relative_to(site).as_posix() for p in (site/'assets').rglob('*') if p.is_file() and p.suffix.lower() not in {'.bvh','.blend'}]
    errors+=['Unexpected asset format: '+p for p in unexpected_assets]
    errors+=['Oversized: '+p for p in oversized]+['Unexpected: '+p for p in forbidden]
    if len(public)>20000:errors.append('More than 20,000 Pages files')
    report={'assets':len(catalog['assets']),'files':len(public),'html_local_links':links,
            'hashes_checked':checked,'max_file_bytes':max(p.stat().st_size for p in public),
            'site_bytes':sum(p.stat().st_size for p in public),'errors':errors}
    write(records/'verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors:raise RuntimeError('Distribution verification failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--download-urls',type=Path)
    parser.add_argument('--release-dir',type=Path,help='Separate directory for GitHub Release ZIPs')
    parser.add_argument('--records-dir',type=Path,help='Private catalog, hash and verification records')
    parser.add_argument('--zip',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    release_dir=(args.release_dir or out.with_name(out.name+'-releases')).resolve()
    records=(args.records_dir or out.with_name(out.name+'-records')).resolve()
    outputs=[out,records]+([release_dir] if args.zip else [])
    for i,path in enumerate(outputs):
        if path.exists():raise FileExistsError('Choose a new output directory: '+str(path))
        if any(path==other or path in other.parents or other in path.parents for other in outputs[i+1:]):
            raise ValueError('Site, releases and records must be separate directories')
    urls=read(args.download_urls) if args.download_urls else {}
    catalog=build(args.plan.resolve(),out,urls,records)
    if args.zip:make_zips(args.plan.resolve(),out,catalog,release_dir,records)
    if args.verify:verify(out,records)
    privacy=audit_tree(out)
    if args.zip:
        zip_privacy=audit_tree(release_dir)
        privacy['site_unique_contents']=privacy.pop('unique_contents')
        privacy['release_unique_contents']=zip_privacy['unique_contents']
        privacy['checked']+=zip_privacy['checked'];privacy['issues']+=zip_privacy['issues']
    write(records/'privacy-verification.json',privacy)
    if privacy['issues']:raise RuntimeError('Publication privacy verification failed')
    print(json.dumps({'site':str(out),'records':str(records),'releases':str(release_dir) if args.zip else None},indent=2))


if __name__=='__main__':main()
