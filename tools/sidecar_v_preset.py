"""24.10: пресет Lightroom/Camera Raw з sidecar .xmp Іри (налаштування її RAW).
Беремо лише глобальні crs-налаштування кадру: колір, тон, криві, профіль; маски, кроп, експозицію, лінзу й ретуш
відкидаємо, бо вони під конкретний кадр. python tools/sidecar_v_preset.py <sidecar.xmp> <вихід.xmp> "<назва>" "<опис>"
"""
import re, sys, uuid

GEN = re.compile(r"^(Crop|HasCrop|AlreadyApplied|RawFileName|Orientation|LensProfile|LensManual|CompatibleVersion|"
                 r"Exposure2012|AutoLateralCA|Perspective|UprightV|Upright|AsShot|DefringePurpleAmount|DefringeGreenAmount|"
                 r"ConvertToGrayscale|ToneMapStrength|HDREdit|EnableMask|RedEye|Retouch|Gradient|Circular|Paint|Mask|Preset|"
                 r"Look|Version$|ProcessVersion$|HasSettings)")
KEEP_EL = ("ToneCurvePV2012", "ToneCurvePV2012Red", "ToneCurvePV2012Green", "ToneCurvePV2012Blue", "PointColors", "Look")


def main(src, out, nazva, opys):
    s = open(src, encoding="utf-8").read()
    head = s[s.index("<rdf:Description"):]
    attrs_end = head.index(">")
    attrs = re.findall(r'crs:([A-Za-z0-9]+)="([^"]*)"', head[:attrs_end])
    body = head[attrs_end + 1:]
    keep = [(k, v) for k, v in attrs if not GEN.match(k)]
    els = []
    for name in KEEP_EL:
        m = re.search(r"\n   <crs:%s>.*?\n   </crs:%s>" % (name, name), body, re.S)
        if m:
            els.append(m.group(0))
    alt = lambda tag, t: ("   <crs:%s>\n    <rdf:Alt>\n     <rdf:li xml:lang=\"x-default\">%s</rdf:li>\n    </rdf:Alt>\n   </crs:%s>"
                          % (tag, t, tag))
    hdr = [("PresetType", "Normal"), ("Cluster", ""), ("UUID", uuid.uuid4().hex.upper()), ("SupportsAmount", "True"),
           ("SupportsAmount2", "True"), ("SupportsColor", "True"), ("SupportsMonochrome", "True"),
           ("SupportsHighDynamicRange", "True"), ("SupportsNormalDynamicRange", "True"), ("SupportsSceneReferred", "True"),
           ("SupportsOutputReferred", "True"), ("CameraModelRestriction", ""), ("Copyright", "Iryna Rul"),
           ("ContactInfo", "instagram.com/irynarul"), ("Version", "17.0"), ("ProcessVersion", "15.4")]
    a = "\n".join('   crs:%s="%s"' % kv for kv in hdr + keep + [("HasSettings", "True")])
    x = ('<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000 1.000000, 0000/00/00-00:00:00        ">\n'
         ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
         '  <rdf:Description rdf:about=""\n    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"\n' + a + ">\n"
         + "\n".join(alt(t, nazva) for t in ("Name", "ShortName", "SortName")) + "\n" + alt("Group", "Iryna Rul") + "\n"
         + alt("Description", opys) + "".join(els) + "\n  </rdf:Description>\n </rdf:RDF>\n</x:xmpmeta>\n")
    open(out, "w", encoding="utf-8", newline="\n").write(x)
    print(out, len(keep), "налаштувань,", len(els), "блоків")


if __name__ == "__main__":
    main(*sys.argv[1:5])
