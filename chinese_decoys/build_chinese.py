#!/usr/bin/env python3
"""
Chinese (cn_ZH / zh_CN) decoys from the platform's forced-alignment delivery (93 work items), in the align-decoys/v1
format laid out like the German / Portuguese / French / Spanish plants files, keyed on work_item_id.

Uses the German builder (german_decoys/build_german.py: same correct-alignment choice, timing checks against both
blind passes, at least 3 words apart, 1 "critical": true per file) with Chinese settings:
  2-3 mistakes per file (3 when the file has 20 or more segments), only these four kinds:
  boundary mismatch   move       minor 40-80 ms, major 100-300 ms, critical 310-700 ms
  missing             delete     (a character gone from the transcript and the chips)
                      remove     (the character stays in the transcript, its chip is gone)
  hallucinated        add        (an extra chip in a pause of at least 0.35 s, repeating the character before)
  wrong transcription replace    one character: a homophone (的 / 地 / 得, 在 / 再, 做 / 作, 那 / 哪, 他 / 她 ...) or the
                                 traditional form of a simplified character (说 -> 說, 国 -> 國: zh_CN is simplified)
No split / join (not used for Chinese), punctuation, capital-letter, digit or speaker-flag mistakes.

Run    : python chinese_decoys/build_chinese.py
Output : chinese_decoys/chinese_decoy_plants.json, chinese_decoys/chinese_skipped.json
"""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "german_decoys"))
import build_german as bg                                              # noqa: E402

GROUPS = [("的", "地", "得"), ("在", "再"), ("做", "作"), ("那", "哪"), ("他", "她", "它"), ("已", "以"), ("像", "象"),
          ("进", "近"), ("到", "道"), ("是", "事", "市"), ("有", "又"), ("就", "旧"), ("和", "合", "河"), ("期", "其"),
          ("会", "回"), ("里", "理"), ("也", "业"), ("力", "立", "利"), ("现", "线"), ("时", "实"), ("工", "公"),
          ("经", "京"), ("正", "政"), ("议", "意"), ("知", "之"), ("题", "体"), ("所", "锁"), ("想", "响"), ("说", "硕"),
          ("能", "龙"), ("年", "连"), ("看", "砍"), ("家", "加"), ("起", "气"), ("后", "候"), ("前", "钱")]
SUBST = {}
for g in GROUPS:
    for i, w in enumerate(g):
        SUBST.setdefault(w, g[(i + 1) % len(g)])
TRAD = dict(zip("说国这个们来时会对门发东车长见进过还为么学问间开关两听头买卖钱电话后实现点经济应该认识让谢请没样务动机场业产万亿与观统总报网线边远运农区医题级华历岁习书读写语议员论设计划认专传达际则变态视规导选战营",
                "說國這個們來時會對門發東車長見進過還為麼學問間開關兩聽頭買賣錢電話後實現點經濟應該認識讓謝請沒樣務動機場業產萬億與觀統總報網線邊遠運農區醫題級華歷歲習書讀寫語議員論設計劃認專傳達際則變態視規導選戰營"))


def traditional(w):
    return TRAD[w] if w in TRAD else None


bg.SEED = 20261113
bg.SHARE = {"move": 0.45, "delete": 0.12, "remove": 0.08, "add": 0.12, "word_substitution": 0.13, "umlaut_replaced": 0.10}
bg.ACCENT_LABEL = "traditional_character"
bg.SUBST, bg.REDUCE = SUBST, {}
bg.FILLERS = {"呃", "嗯", "啊", "哦", "额", "唉", "呀"}
bg.umlaut = traditional
bg.MIN_WORD_LEN = 1
bg.TARGET_FN = lambda n: 3 if n >= 20 else 2
bg.SPEAKER_FLAG = False
bg.RETRIES = 30

if __name__ == "__main__":
    bg.main(HERE / "deliveries", HERE.parent / "hindi_decoys" / "alignment-decoys-template.json", HERE, "chinese")
