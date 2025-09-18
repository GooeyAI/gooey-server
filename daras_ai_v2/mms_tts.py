"""
To deploy changes to remote functions, run this file directly as a script:

```bash
poetry run python daras_ai_v2/mms_tts.py
```
"""

import modal
from decouple import config


MMS_TTS_SUPPORTED_LANGUAGES = {
    "abi", "abp", "aca", "acd", "ace", "acf", "ach", "acn", "acr", "acu", "ade", "adh", "adj", "adx", "aeu", "agd",
    "agg", "agn", "agr", "agu", "agx", "aha", "ahk", "aia", "aka", "akb", "ake", "akp", "alj", "alp", "alt", "alz",
    "ame", "amf", "amh", "ami", "amk", "ann", "any", "aoz", "apb", "apr", "ara", "arl", "asa", "asg", "asm", "ata",
    "atb", "atg", "ati", "atq", "ava", "avn", "avu", "awa", "awb", "ayo", "ayr", "ayz", "azb", "azg", "azj", "azz",
    "bak", "bam", "ban", "bao", "bav", "bba", "bbb", "bbc", "bbo", "bcc", "bcl", "bcw", "bdg", "bdh", "bdq", "bdu",
    "bdv", "beh", "bem", "ben", "bep", "bex", "bfa", "bfo", "bfy", "bfz", "bgc", "bgq", "bgr", "bgt", "bgw", "bha",
    "bht", "bhz", "bib", "bim", "bis", "biv", "bjr", "bjv", "bjw", "bjz", "bkd", "bkv", "blh", "blt", "blx", "blz",
    "bmq", "bmr", "bmu", "bmv", "bng", "bno", "bnp", "boa", "bod", "boj", "bom", "bor", "bov", "box", "bpr", "bps",
    "bqc", "bqi", "bqj", "bqp", "bru", "bsc", "bsq", "bss", "btd", "bts", "btt", "btx", "bud", "bul", "bus", "bvc",
    "bvz", "bwq", "bwu", "byr", "bzh", "bzi", "bzj", "caa", "cab", "cac", "cak", "cap", "car", "cas", "cat", "cax",
    "cbc", "cbi", "cbr", "cbs", "cbt", "cbu", "cbv", "cce", "cco", "cdj", "ceb", "ceg", "cek", "cfm", "cgc", "che",
    "chf", "chv", "chz", "cjo", "cjp", "cjs", "cko", "ckt", "cla", "cle", "cly", "cme", "cmo", "cmr", "cnh", "cni",
    "cnl", "cnt", "coe", "cof", "cok", "con", "cot", "cou", "cpa", "cpb", "cpu", "crh", "crk", "crn", "crq", "crs",
    "crt", "csk", "cso", "ctd", "ctg", "cto", "ctu", "cuc", "cui", "cuk", "cul", "cwa", "cwe", "cwt", "cya", "cym",
    "daa", "dah", "dar", "dbj", "dbq", "ddn", "ded", "des", "deu", "dga", "dgi", "dgk", "dgo", "dgr", "dhi", "did",
    "dig", "dik", "dip", "div", "djk", "dnj", "dnt", "dnw", "dop", "dos", "dsh", "dso", "dtp", "dts", "dug", "dwr",
    "dyi", "dyo", "dyu", "dzo", "eip", "eka", "ell", "emp", "enb", "eng", "enx", "ese", "ess", "eus", "evn", "ewe",
    "eza", "fal", "fao", "far", "fas", "fij", "fin", "flr", "fmu", "fon", "fra", "frd", "ful", "gag", "gai", "gam",
    "gau", "gbi", "gbk", "gbm", "gbo", "gde", "geb", "gej", "gil", "gjn", "gkn", "gld", "glk", "gmv", "gna", "gnd",
    "gng", "gof", "gog", "gor", "gqr", "grc", "gri", "grn", "grt", "gso", "gub", "guc", "gud", "guh", "guj", "guk",
    "gum", "guo", "guq", "guu", "gux", "gvc", "gvl", "gwi", "gwr", "gym", "gyr", "had", "hag", "hak", "hap", "hat",
    "hau", "hay", "heb", "heh", "hif", "hig", "hil", "hin", "hlb", "hlt", "hne", "hnn", "hns", "hoc", "hoy", "hto",
    "hub", "hui", "hun", "hus", "huu", "huv", "hvn", "hwc", "hyw", "iba", "icr", "idd", "ifa", "ifb", "ife", "ifk",
    "ifu", "ify", "ign", "ikk", "ilb", "ilo", "imo", "inb", "ind", "iou", "ipi", "iqw", "iri", "irk", "isl", "itl",
    "itv", "ixl", "izr", "izz", "jac", "jam", "jav", "jbu", "jen", "jic", "jiv", "jmc", "jmd", "jun", "juy", "jvn",
    "kaa", "kab", "kac", "kak", "kan", "kao", "kaq", "kay", "kaz", "kbo", "kbp", "kbq", "kbr", "kby", "kca", "kcg",
    "kdc", "kde", "kdh", "kdi", "kdj", "kdl", "kdn", "kdt", "kek", "ken", "keo", "ker", "key", "kez", "kfb", "kff",
    "kfw", "kfx", "khg", "khm", "khq", "kia", "kij", "kik", "kin", "kir", "kjb", "kje", "kjg", "kjh", "kki", "kkj",
    "kle", "klu", "klv", "klw", "kma", "kmd", "kml", "kmr", "kmu", "knb", "kne", "knf", "knj", "knk", "kno", "kog",
    "kor", "kpq", "kps", "kpv", "kpy", "kpz", "kqe", "kqp", "kqr", "kqy", "krc", "kri", "krj", "krl", "krr", "krs",
    "kru", "ksb", "ksr", "kss", "ktb", "ktj", "kub", "kue", "kum", "kus", "kvn", "kvw", "kwd", "kwf", "kwi", "kxc",
    "kxf", "kxm", "kxv", "kyb", "kyc", "kyf", "kyg", "kyo", "kyq", "kyu", "kyz", "kzf", "lac", "laj", "lam", "lao",
    "las", "lat", "lav", "law", "lbj", "lbw", "lcp", "lee", "lef", "lem", "lew", "lex", "lgg", "lgl", "lhu", "lia",
    "lid", "lif", "lip", "lis", "lje", "ljp", "llg", "lln", "lme", "lnd", "lns", "lob", "lok", "lom", "lon", "loq",
    "lsi", "lsm", "luc", "lug", "lwo", "lww", "lzz", "maa", "mad", "mag", "mah", "mai", "maj", "mak", "mal", "mam",
    "maq", "mar", "maw", "maz", "mbb", "mbc", "mbh", "mbj", "mbt", "mbu", "mbz", "mca", "mcb", "mcd", "mco", "mcp",
    "mcq", "mcu", "mda", "mdv", "mdy", "med", "mee", "mej", "men", "meq", "met", "mev", "mfe", "mfh", "mfi", "mfk",
    "mfq", "mfy", "mfz", "mgd", "mge", "mgh", "mgo", "mhi", "mhr", "mhu", "mhx", "mhy", "mib", "mie", "mif", "mih",
    "mil", "mim", "min", "mio", "mip", "miq", "mit", "miy", "miz", "mjl", "mjv", "mkl", "mkn", "mlg", "mmg", "mnb",
    "mnf", "mnk", "mnw", "mnx", "moa", "mog", "mon", "mop", "mor", "mos", "mox", "moz", "mpg", "mpm", "mpp", "mpx",
    "mqb", "mqf", "mqj", "mqn", "mrw", "msy", "mtd", "mtj", "mto", "muh", "mup", "mur", "muv", "muy", "mvp", "mwq",
    "mwv", "mxb", "mxq", "mxt", "mxv", "mya", "myb", "myk", "myl", "myv", "myx", "myy", "mza", "mzi", "mzj", "mzk",
    "mzm", "mzw", "nab", "nag", "nan", "nas", "naw", "nca", "nch", "ncj", "ncl", "ncu", "ndj", "ndp", "ndv", "ndy",
    "ndz", "neb", "new", "nfa", "nfr", "nga", "ngl", "ngp", "ngu", "nhe", "nhi", "nhu", "nhw", "nhx", "nhy", "nia",
    "nij", "nim", "nin", "nko", "nlc", "nld", "nlg", "nlk", "nmz", "nnb", "nnq", "nnw", "noa", "nod", "nog", "not",
    "npl", "npy", "nst", "nsu", "ntm", "ntr", "nuj", "nus", "nuz", "nwb", "nxq", "nya", "nyf", "nyn", "nyo", "nyy",
    "nzi", "obo", "ojb", "oku", "old", "omw", "onb", "ood", "orm", "ory", "oss", "ote", "otq", "ozm", "pab", "pad",
    "pag", "pam", "pan", "pao", "pap", "pau", "pbb", "pbc", "pbi", "pce", "pcm", "peg", "pez", "pib", "pil", "pir",
    "pis", "pjt", "pkb", "pls", "plw", "pmf", "pny", "poh", "poi", "pol", "por", "poy", "ppk", "pps", "prf", "prk",
    "prt", "pse", "pss", "ptu", "pui", "pwg", "pww", "pxm", "qub", "quc", "quf", "quh", "qul", "quw", "quy", "quz",
    "qvc", "qve", "qvh", "qvm", "qvn", "qvo", "qvs", "qvw", "qvz", "qwh", "qxh", "qxl", "qxn", "qxo", "qxr", "rah",
    "rai", "rap", "rav", "raw", "rej", "rel", "rgu", "rhg", "rif", "ril", "rim", "rjs", "rkt", "rmc", "rmo", "rmy",
    "rng", "rnl", "rol", "ron", "rop", "rro", "rub", "ruf", "rug", "run", "rus", "sab", "sag", "sah", "saj", "saq",
    "sas", "sba", "sbd", "sbl", "sbp", "sch", "sck", "sda", "sea", "seh", "ses", "sey", "sgb", "sgj", "sgw", "shi",
    "shk", "shn", "sho", "shp", "sid", "sig", "sil", "sja", "sjm", "sld", "slu", "sml", "smo", "sna", "sne", "snn",
    "snp", "snw", "som", "soy", "spa", "spp", "spy", "sqi", "sri", "srm", "srn", "srx", "stn", "stp", "suc", "suk",
    "sun", "sur", "sus", "suv", "suz", "swe", "swh", "sxb", "sxn", "sya", "syl", "sza", "tac", "taj", "tam", "tao",
    "tap", "taq", "tat", "tav", "tbc", "tbg", "tbk", "tbl", "tby", "tbz", "tca", "tcc", "tcs", "tcz", "tdj", "ted",
    "tee", "tel", "tem", "teo", "ter", "tes", "tew", "tex", "tfr", "tgj", "tgk", "tgl", "tgo", "tgp", "tha", "thk",
    "thl", "tih", "tik", "tir", "tkr", "tlb", "tlj", "tly", "tmc", "tmf", "tna", "tng", "tnk", "tnn", "tnp", "tnr",
    "tnt", "tob", "toc", "toh", "tom", "tos", "tpi", "tpm", "tpp", "tpt", "trc", "tri", "trn", "trs", "tso", "tsz",
    "ttc", "tte", "ttq", "tue", "tuf", "tuk", "tuo", "tur", "tvw", "twb", "twe", "twu", "txa", "txq", "txu", "tye",
    "tzh", "tzj", "tzo", "ubl", "ubu", "udm", "udu", "uig", "ukr", "unr", "upv", "ura", "urb", "urd", "urk", "urt",
    "ury", "usp", "uzb", "vag", "vid", "vie", "vif", "vmw", "vmy", "vun", "vut", "wal", "wap", "war", "waw", "way",
    "wba", "wlo", "wlx", "wmw", "wob", "wsg", "wwa", "xal", "xdy", "xed", "xer", "xmm", "xnj", "xnr", "xog", "xon",
    "xrb", "xsb", "xsm", "xsr", "xsu", "xta", "xtd", "xte", "xtm", "xtn", "xua", "xuo", "yaa", "yad", "yal", "yam",
    "yao", "yas", "yat", "yaz", "yba", "ybb", "ycl", "ycn", "yea", "yka", "yli", "yor", "yre", "yua", "yuz", "yva",
    "zaa", "zab", "zac", "zad", "zae", "zai", "zam", "zao", "zaq", "zar", "zas", "zav", "zaw", "zca", "zga", "zim",
    "ziw", "zlm", "zmz", "zne", "zos", "zpc", "zpg", "zpi", "zpl", "zpm", "zpo", "zpt", "zpu", "zpz", "ztq", "zty",
    "zyb", "zyp", "zza"
}  # fmt: skip


app = modal.App("gooey-mms-tts-runner")

cache_dir = "/cache"
model_cache = modal.Volume.from_name("hf-model-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim()
    .pip_install(
        "transformers~=4.44",
        "huggingface_hub[hf_transfer]~=0.34.4",
        "torch~=2.5.1",
        "scipy~=1.11",
        "python-decouple~=3.6",
    )
    .env({"HF_HUB_CACHE": cache_dir, "HF_TOKEN": config("HF_TOKEN", cast=str)})
)


def load_pipe(language: str):
    import torch
    from transformers import pipeline

    has_cuda = torch.cuda.is_available()
    if has_cuda:
        print("Using GPU")
    else:
        print("GPU not available, using CPU")

    pipe = pipeline(
        "text-to-speech",
        model=f"facebook/mms-tts-{language}",
        tokenizer=f"facebook/mms-tts-{language}",
        device=0 if torch.cuda.is_available() else -1,
    )

    return pipe


@app.function(
    image=image,
    gpu="a10g",
    timeout=30 * 60,
    volumes={"/cache": model_cache},
    enable_memory_snapshot=True,
)
def run_mms_tts(language: str, text: str) -> bytes:
    import io
    import torch
    import scipy

    pipe = load_pipe(language)

    print("Running inference")
    with torch.no_grad():
        output = pipe(text)

    b = io.BytesIO()
    scipy.io.wavfile.write(b, rate=output["sampling_rate"], data=output["audio"][0])
    return b.getvalue()


if __name__ == "__main__":
    with modal.enable_output():
        app.deploy()
