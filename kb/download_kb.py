import subprocess, sys, os, re, json, urllib.request, urllib.parse, time

TOKEN = sys.argv[1]
SKILL_DIR = "C:/Users/admin/.workbuddy/plugins/cache/workbuddy-builtin/skill-library/0.5.9"
OUT_DIR = "C:/Users/admin/WorkBuddy/2026-08-14-09-03-20/kb/raw"
os.makedirs(OUT_DIR, exist_ok=True)

# (node_id, title)
NODES = [
    ("dPY8a73jQkkoIuxGFAtGHk", "产品卖点总结"),
    ("x5SPGGbipwdJibpP3O4pCY", "地推合作话术-喜客丸品牌"),
    ("jwlQgM3VXbblyrAUr9kAKX", "拓店人员目标门店选择标准"),
    ("M6kby46tDkWRmhlZ2mOoO0", "be971234fcca7a95e4dadb0920273d0e"),
    ("X2nm2JKqyr2NnROqclpQHU", "抖音来客及云连锁知识体系"),
    ("DnCQESKSVBhAddqroD54X1", "拓店信息登记表"),
    ("pWCfNopS4ucpghR4hM60lH", "e8fccdd580606aaadcb5ac3abd6fcf68"),
    ("4e3GIXInQRo4pckMupct8e", "个体工商户办理预包装流程"),
    ("vXJ1d0T9MavUyOTzGQ4CQb", "五指毛桃花胶肉丸文案包装策划"),
    ("cO6dUBPHU4X0mFb9oEolYL", "五指毛桃肉丸文案包装策划"),
    ("n2PiSmoWVCIfoCvoApZ9uz", "灵芝肉丸"),
    ("MKWnXp2LcwxDcuK9DyP30T", "90388d66209fbe72c4f012d297d11003"),
    ("ruHTjpcSZbn01agDXrx7w2", "喜客丸品牌定位"),
    ("BGIaZVGkKY2Qh1BrKScrKe", "d6f598514cc45a4eb959dd8072374d32"),
    ("sgclN69OL5nTIdQDB0f7UA", "五指毛桃海参肉丸"),
    ("mkckLpYoi5ATb44OnJ2hQT", "f9acc84fc0468adee6a017cf76065090"),
    ("vpeWX8SjVfNYo9Aytx8uXR", "西洋参肉丸"),
    ("fy0O6r442yV1UfbZVKvHIk", "喜客丸为什么选用客家猪肉不用牛肉鱼肉"),
    ("t5qfBMfpClD13IfVVsJ06k", "9b8b1a73e5451d3e6e25ec40a738d37d"),
    ("Wti9smsWbaFBLRiAgbgX3N", "喜客丸产品优势介绍"),
    ("mf0lmoEFOrtIdPaGiSUPCl", "客家百年传承1拷贝"),
    ("RT2nmNcIVs75kvSOiw6X2x", "1_17"),
    ("7lwgy3XhiQLoMnBgd2dZQw", "1_18"),
    ("ImLii5j9s2ycnLCwXp3qlr", "客家百年传承4拷贝"),
    ("Z4XE2TkQeDa8xz7J7Fc79F", "微信图片_20260724141501_117_24"),
    ("BbN6DI11G0aKNanpeCNMb9", "1_16"),
    ("DFexJPKwEPn9oTIDziK1Wj", "丸子"),
    ("LL3yEWrGJKP3Qr3obMQ8on", "微信图片_20260723170803_113_24"),
    ("kwQVJWG7TkhVzKnK0qaZXu", "未标题-1拷贝"),
    ("MsMSB9yoSnj4fLxsAyuPIj", "微信图片_20260723150222_96_24拷贝"),
    ("LzIKC8InUVBbUhgA9faOqj", "微信图片_20260724141506_118_24"),
    ("5PKeOoszlkSlrDJvvQ730P", "微信图片_20260727015245_48_1拷贝"),
    ("60y4Ic3eMgFRGyrPYy4xTA", "微信图片_20260727090726_49_1拷贝"),
    ("No0W04IEya29XYj55Yu81N", "微信图片_20260724141508_119_24"),
    ("ClLVJhLiJz3ImKDAoQHVYT", "口感"),
    ("RUjWvyTApKUYCnAdnYUKGo", "微信图片_20260724141518_120_24"),
    ("GHnNBYLkiooip9te4knWZ5", "丸子2"),
    ("B5zp6UWWqcpwOoFNjZ1L0t", "客家土猪丸拷贝"),
    ("kBITMX38UIbRfAe5MCTlWw", "话术框架-本地生活"),
]

def sanitize(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

def get_link(node_id):
    p = subprocess.run(
        ["python3", os.path.join(SKILL_DIR, "drive", "get_download_link.py"),
         "--token-stdin", "--node-id", node_id],
        input=TOKEN, capture_output=True, text=True, timeout=60)
    m = re.search(r'KS_DRIVE_DOWNLOAD\s+(\{.*\})', p.stdout)
    if not m:
        return None, None, p.stdout
    obj = json.loads(m.group(1))
    return obj.get("download_url"), obj.get("ext"), obj.get("file_name")

def main():
    ok, fail = 0, 0
    for nid, title in NODES:
        try:
            url, ext, fname = get_link(nid)
            if not url:
                print(f"[SKIP] {title}: no link\n{p.stdout[:200]}")
                fail += 1
                continue
            ext = ext or (os.path.splitext(fname)[1].lstrip('.') if fname else "")
            out_name = f"{sanitize(title)}.{ext}" if ext else sanitize(title)
            out_path = os.path.join(OUT_DIR, out_name)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(out_path, "wb") as f:
                f.write(data)
            print(f"[OK] {out_name} ({len(data)} bytes)")
            ok += 1
        except Exception as e:
            print(f"[ERR] {title}: {e}")
            fail += 1
        time.sleep(0.2)
    print(f"\nDONE ok={ok} fail={fail}")

if __name__ == "__main__":
    main()
