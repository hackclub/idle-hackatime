"""Hackatime for Python IDLE.

Tracks coding time in IDLE editor windows and sends WakaTime-compatible
heartbeats to Hackatime through wakatime-cli.

Install with the Python that runs IDLE:

    python3 IdleHackatime.py install

Remove with:

    python3 IdleHackatime.py uninstall
"""

import base64
import configparser
import json
import logging
import os
import platform
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile

__version__ = "1.0.0"

EXTENSION_NAME = "IdleHackatime"
DEFAULT_API_URL = "https://hackatime.hackclub.com/api/hackatime/v1"
HEARTBEAT_INTERVAL_SECONDS = 120
STATUS_REFRESH_MS = 2000
TODAY_REFRESH_SECONDS = 60
CLI_TIMEOUT_SECONDS = 60
CLI_DOWNLOAD_URL = (
    "https://github.com/wakatime/wakatime-cli/releases/latest/download/"
    "wakatime-cli-{os}-{arch}.zip"
)

HOME_FOLDER = os.path.realpath(
    os.environ.get("WAKATIME_HOME") or os.path.expanduser("~")
)
RESOURCES_FOLDER = os.path.join(HOME_FOLDER, ".wakatime")
CONFIG_FILE = os.path.join(HOME_FOLDER, ".wakatime.cfg")
LOG_FILE = os.path.join(RESOURCES_FOLDER, "idle-hackatime.log")
IDLE_CONFIG_FILE = os.path.join(
    os.path.expanduser("~"), ".idlerc", "config-extensions.cfg"
)

PYTHON_EXTENSIONS = (".py", ".pyw", ".pyi")

log = logging.getLogger("idle-hackatime")

# Monochrome Hackatime logo, keyed by (colour, pixel size).
LOGO_PNG = {
    ("black", 16): (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAQAAAC1+jfqAAABI0lEQVQoz13RzyvfcRwH8MfH"
        "x1I76KulpdUO0tQKff2ItJxx2mFOysEkJ/kDxEH5A4ja0VlOttqBlvxIuThshzWH5UiEEha9"
        "dvi8fYvXq1evev189nxSWFWKTt14IZN5ZiXVmLf2tJynXFbSYcpHbRpdufDaZdHK0Kxs1oWo"
        "+DcdWpFVyVBjSYN/wn262KNXyETx5KtVjWn3wB9hzJzNBNwb4bMm4digbj+F3LLwrpgoY8SR"
        "dT/kWvw1oM44PlCNl+izaEarMw8WXNmTo1QA6hTuhfAdtU6FcCcMPbLxS7gW9sGKcCNcq6d4"
        "0i88CLtemdQu3ArTqSvHhBB2vBe6bAhfEokVwntsOXEonNs2WmH5iSZvDfutN+n7TM88DX3y"
        "iAz8B7/uWWzs4mOKAAAAAElFTkSuQmCC"
    ),
    ("black", 20): (
        "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAQAAAAngNWGAAABlklEQVQoz23SMWsUURQF4G8m"
        "owY0JGFNsaCCYMQgBBQFsYiIpghoI9gZtU1Au2CnW1kJdlEw2PgTgiKJIKZQBFOJKLETDYiS"
        "TbFFNu7OtZjZdZGc4j0e97x7OOde/iGVSHHUKFI7IumSeeIVUplU0qmkJS1kzjgmjBhxxEm5"
        "llyIbhMJhl0x7rzPGkJoe2/GuAlDPXr2uKDqvnpJagkhLDnkqgz6kGgZsyCz6bC2kKGFqp+W"
        "DatLOm2/+oDvQktoqsuFWTWr9hXiGa4JEwa0hfDanEdCGDYpzCArxBeFafwQ7up3ykPhaVl5"
        "27GTWSufl4Vpd9z2wAucFsKGSuG53zchzEucdcmUKRdxzroQthzspLgq/BHqfrkBXtoUpbXf"
        "hkj1YQWhbdB+VfDRoG05+GRTWgxxTMjltoUadhstI28K1wvXxVETmprCPYklLAsNYaV3hAkW"
        "hFyYUxVuOiCELyq9K1f8uGVDeGNe2LIoPLO3HHPPPqaomPXcmoZ3HjvB/7QCWXnvsu54SUrs"
        "iEQmw6SBMrgu/gIFhpUDOW/fugAAAABJRU5ErkJggg=="
    ),
    ("black", 24): (
        "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAACDElEQVQ4y33TTYjNYRQG8N/9"
        "3zszJc2UcGMmxILGYEIZ+UqkmIWyEgtKSk3yUXY2srJU7BRJyEcp0iTZSNkMGybMRs1GjZHv"
        "Mffjfyzuf+69Pp9389Y5z/s+55zn8CtySFA0I7v9B0lGacVNj7VJ/qQkTbdUq3lCCSyQk0oV"
        "fs3L16WEpbb4ZJFeh+xQtM57477Jm25SrqG59vomMw0ruGNhk4Jx1wwKnzyRSBuyllun3RkT"
        "QllZKlRUhHBPm326G8JyKNrtsWFnharITipVUnEK22qZSUYouWyFZWaRUVLkVLQ4ptNdH+sF"
        "yOOCsAEjQlkIL53zWQhzdQnXp1qUYI4vQi9eCeGp9VY7Zky4j/1C1RIktdFsNB3deIjX9nir"
        "x0szcRIHkNheI8BicBjHjapaYUCHHq/0e2aX9UpYjmyObZjU57wB8+z03bCvvusW+l3Myu1A"
        "1ChHhLKqMOq2B2aB0x55LoSqinAJhYLAEBKJqi5dKBrDuM1IkajgRbOh32TdryoLK8FsH4Q0"
        "G2FYOjXrAg4Kk/XQWqzC1WwqJeFOk1XlMCj8yP5ZI/FOUZ9QVRImzG82eYJphoSySWGlbuEW"
        "bmSu2lLvaNNetLiShfsNCOGAa8KINb+nN1Zpq/sm6m4No05o+1t6rZIaqdMOR004Z1Hmz7x/"
        "Il8PjtqLvMKUqf+NRAt6tTc2oIGfxCDH89IByhkAAAAASUVORK5CYII="
    ),
    ("black", 32): (
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAQAAADZc7J/AAADGklEQVRIx5XVW4hVZRQH8N++"
        "qGGOiUPJFE6oFJYZRmlZGYigEIo+iBK9ZCRkvShEFykDiSISsttLD2VQUUEgVNjlpZAeCiwT"
        "yqACL0lJTGri6Mycs1cP5zt7zhlH0LUf9t583/qvtf7r/62vcGHL0CNUMpdkWXIoscNryC/F"
        "ubU5V2CBYeGBBHYRVoB+vel/kvedNjetFTK5ojufouu7qd86M01B6TbbrVZ40DF/GhQIIeTi"
        "/Og57rTBvcgccCJtbj2n7bHaZMusd/OYwLX73Ta5yUybfS6EhqZKpamZYP6ySq8t7hoLkWGa"
        "rVjkOUeFhqorg0rDsPChq83wtOnJK+FkuNxk/R72iJdNdY2ou1/JEn0N8w343u8WO6joZGIC"
        "NghhoxldsUOkEiphm8PWmuf2bnXk6POv8AQeEkY6WDhYu4eplgnnzOkGKPGq8LcePJsAWnHP"
        "eMouoSHsBd8K77XLz5FpmG49TmnUyCH3mVVuNOAoKryBee7AetdptnMosFYIA3qxUjgrvC3H"
        "Zr1+EcLPSjwpDAqPjQq8xEvJaSVy+4RTrrTaOtvdY60w5FZMckgYFna3QucI9KdmbkPlfidM"
        "tdR8sx2xyBqHLLQPW12rocAsNEeZvAylhoVex6+usslxTQMmOu4VsxzABtvqxKeYgKx9TE8h"
        "lCqPWuBd+531nxfMdNRcS/S43jpLqQU2rNnZxGc6et+Wz4uprFs6BFXVe75p9avNwbd1+wpN"
        "DcMYRCn3o+8wpClP0QM/jAJU2OuQXJUgSjmmIRT4IA2UzsP3aQKqi3hcGKqTHRHerAnrc6YW"
        "c6uAn7qnQYYJ/qh5aL3fAjvNwcdj1tYYMycLLO4gcUTYhWnCTqyoz8Y54Z3xZlKJ+0TS2Yjw"
        "EZYLDTfgS2HEsLBX1h4n50OsMSQ0nBO+wvMitWxFKuATpQveFCVm+yJt/c0SX6eM9vhHOGlL"
        "XbALQ7DcbifHTKXDtuszevV08N9tbWXMsMBcfTY6YoeD9qvSebkIGxVNZtCxOrtxKh//zmum"
        "VEtDdhvERCMXF7vbMlyhZ/ymtex/KwFiHbOuDN4AAAAASUVORK5CYII="
    ),
    ("black", 40): (
        "iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAQAAAAm93DmAAAENElEQVRIx6XWWahVVRgH8N/e"
        "59yc4oqm1yQtDJsjs2wUwQcLsiKIqIyKUHooCoyIBoh6SEuLsiwaXjQKGl5sjnqojKygUJqx"
        "6UEUm7w06fWes8/+ejj7nLPvcPRCa8He56z9rf/6xv/6GNuooCIZm+DBRo/cHeb7lLFAdhut"
        "rSnm+kvmZhMPDpl21TuKzQmW6VVxtn1d5MdwxERzJW2X9NooLFZFRbWQSaQj9R2+UJVJXecY"
        "P9vtPfv0me15hxtvvE2uVCvkcnmhQN5duyrmWucacLRXva5flGa/991iFjjKAhMcILAVnOVh"
        "HO0uPF2A5Boacrm8WBn0kJvc4AJPmt8NMsXx1kncKbXcNiGTFSCtZy5TL2AP12OSxx0/enBT"
        "rDELp3nWR8L+IcaWZ25QeMVp+syzthyLDnJgt/EWutG1DrPSONHFOYkeXGKOxb7wo3PESB2b"
        "Z2wRwg9YK9rGNWfW9mEI/3hJOB3zXDiaH6tYLoSvTMZ2oVECaP6utz36J54UNrlvtKAkmG6P"
        "8LuZmOnPdihCpia87NsCMhO2gPeEAUd2nNeyvIJbTcVndqNXb9u3uYoe7LDBJlW5wAvgQ4y3"
        "uhOWVhFlDnUV2FmsN+s4JFJvWqbPLrt9j4aq3zyLxDKEy83RKIelgouLRHkFTPar0JAL14GL"
        "TXSvUDMo3A/OaKfQrUUUSgF5RBgQtktUsUHYK6zT6zw8Zzl2CmGHCVI8JdTVhXeGJneKd4Wa"
        "TFgKjrBXCAsc5Xb3W+E2x9gg7HEymKNeFGbY0eLKJmqOvrbnVqFil6UGsMilwnfG6XeFM33k"
        "BF/rwWOqMokE00zrACZIHaLJcJlTPaOBzU60xmRbXKpf1Xzb3WKR31D3gIs0VIv9Exw6PBO3"
        "FvnVfL5hnklgNmZYbK5xBW1Ndr7NpbRvUsYQikjxVhuw9d7hY/t8UTr0G/0+93tJplU3/5hZ"
        "pogq1gyp3U7d/lgQ/yFY3S7DDlxT0x9axqdtpnm/fIKKRK6OTIZcA2+jLqRDqjfHVplKh52a"
        "bt05jA6iSIgJSIpr/ssRMk27rm4ldkvDqgEb0BhBGb0mIS2+bCw06oxQ9avXhu9NMNWeYRyY"
        "C3tMASeZjiMNllgohJpw99DC6wRmhVAriefCv2aAL90DXh0WvPCTcUbtKFI8LwwOAfzbDPTZ"
        "r98ULBmRXgt1ufeaZ3wgDJbuur1mY6kQ1oPNJZoNK0Yzt6xjxZtCXjLrdKwvvHUujpMX/8L1"
        "DtLBNT+uKgyqy4RT8Enhiq36rDQghF+cfzC4TiKdaXNbwy0e1S/kam3Na54w5UDGDvVlU2yJ"
        "F/0xyjW/3YOObWfGqIEYzfSQY6oFTnasXotM87ifbLNNDVWNro1AV9COfybaVRRYU7OujeeB"
        "OtKGhkRFj1SuH/vRI5EdqCccy6jiMm/7X037yDEmsP8ADv8kRJw7ONUAAAAASUVORK5CYII="
    ),
    ("black", 48): (
        "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"
        "/4ho/p+V/gvgdNTlYxaMeAAAAABJRU5ErkJggg=="
    ),
    ("white", 16): (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAQAAAC1+jfqAAABLUlEQVQoz02PvSuFARyFn/d9"
        "r5TBR6IkBolS1PWRm2R2jWJSBiST0SQG/wFRRmVQRpSBJB+R5Q4MYsBIJCVf130M9xVn+Q3n"
        "OZ3zCwSAkBwhOdqJOKWALGDeyCtHKSHQzxTwhcTJIL5JpIY0vVSyxioZSrgFwEBsNOmsz/5p"
        "yzZbxCAkAApZpIpPJBtXpuhCAsRI3HTdujh75pU65py7YohYrY5ar97ZZ6fnauSS2iAhkASG"
        "uWaDPSKauSFNGeNANySAIqCHBWZo4ZFv5nnhmAgoBcR2Navqtljsg6of6qAg4oX6qp6IuKK+"
        "qa9WCCbEXvVbPbLcSVvVd3VaTPw+OqHqoU1qhzvqshj8VkRiyn3vzahPHjgi/4E8grUOeWmX"
        "iKGB/AEYxdCAmF+GyA+lWAN/SbbaEAAAAABJRU5ErkJggg=="
    ),
    ("white", 20): (
        "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAQAAAAngNWGAAABtklEQVQoz1WSv2sUURSFv/d2"
        "TAIakrCmWNDYiApCQEGQFBHRFAvaiGJj0DYB0wXLpLKyjhIVC/8EfyBRCKZQAgYLESXpRIKg"
        "ZANusasz81nMjK7nFq94h3vP4ZwgfxGRQM4RZItITi8sJpRvFO/7SowmRkP1EwEISMJpjiGj"
        "jHKYk+Sk5IiEamMQR7zkuGf9ZFvVzHVnHHfS4YJRHOz3nA1v2ypJqQVWHPOKSXU60KWfpxzl"
        "PZCRUwNScia4zDpjhbhC7JbvxK9qqnZtmauzLrrhPjFgIl5TJx00U3XVee+qOuKUOiMmEYGr"
        "wCF+8g1YoMkqHeARLeaAaSBDTNxU34gX1WlvOecdn4unVN2xXrge8IuqSwYnvGDTpufFM26r"
        "2vGgFGY21N9qy+9eF/GFu1pa++GwRGrAGiAZQ+ynAcAHhvhVpv2RXWIR/TKQEEmBAaCPZaCP"
        "SAY8LAtjIi6qXbvqgsEV8aXaVtd6IwziAzVX522oNzyg6mfrRad6S3bTHfW1S2rHJ+pj94o1"
        "saePUaw76zM3bfvWe56QivaPWGlF3OO2x0tSVej/iBhMTMQpB43VrmL+AB4Yqsh1NPTKAAAA"
        "AElFTkSuQmCC"
    ),
    ("white", 24): (
        "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAACQklEQVQ4y3WTXWiOcRjGf8//"
        "fbeV1hwwCwtxQNvMQlG+8pFiB8qROKB2uMSUMydyJKUUZ4qkyEcRaUlKS+1klGwNJ2onsrYw"
        "bbzv+zw/B8//3buR+z577ut6/vd1X/edyLxIkEBGC2UmCWT8HdYyiJhYL953wAZD/DYnwywz"
        "kFHPCqQEwCoSMjKKsVptwVor7XTxjkYWsYcjNPOKywwySYEFTJFgjRDI2MViRijyiNVzOp7g"
        "Dv3Id15HRbH3TrfZ5EVn1LJlM7ViRdWnNnjcthyZy8QWjzjgiFfU1GpkZpaseF7cnyMDkAAl"
        "brGB9TQDkiIZkFChjj6W84RvESkWxOvqDvGTWlZ12Kv+UHWZrerdHJkrWOqU2iWOqjrodjfb"
        "57j6TDyhpq4TQyAAO2kE2oAXwAeO8pkOhlkMnAN6gMABIOSGrAXgJHCGMVI20MtCOhilmzcc"
        "ZjsloBOIPjYAv9nKNXpZwSGmGeEn07Qh3dyIchfmkoviKbVsqo750Oc2i3jBl75VNbWi3hSL"
        "RQSGgEAgpZVWoIVxYILdQAYEKsD7fFsTMfgxGpZaVjeKuMRJNYsWans+JSmScQmoAIFC1LSJ"
        "r/QDKVAm4THDFMiwuhz96q/4zhaDX2xxq5paUmdcWdul3LwFDqllf6sbbVMfiPfiVu2N45m9"
        "uIJY5+1Y7rZX1R7vqJ/cUoU750QLIu7zmTPWYsyzNtTgzrvpJJKWe9DTznjVNSZzfvYPIS9V"
        "i2MeEwsWI+k/hHwEdWKXTXF+8/IPuIUb2jbkvPMAAAAASUVORK5CYII="
    ),
    ("white", 32): (
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAQAAADZc7J/AAADZElEQVRIx4WVX2hWdRjHP+fP"
        "XFDa2KqxYoaOambBIrSsDCTYbpQGDSW6SchAKlAISqkVEkXkhUVRV2VQkkEglP2ToFheeLGy"
        "QS2IYipUI6au5dz2vud8unh/591551bP7+Kcw/k9f77Pn+8TyZISIcuZoULEktciF1MEgZQq"
        "+2nmCWLyJd3YeCJjEWMTscc59WExlcVP42ci4krbwnezh5yyO/xLjIxNgotwyhASMlbSxyy/"
        "8xtTrOFR+omp8DhHOVsKuwRp3kBMzl3cxDifEvEDnbSUVP7hW97iGBu4ilFGSMgacxCL97jT"
        "W+x0l5+rWjUzNzczsyZ/uMU2d3t3HS5F6rDFveJ6X/CMWjW3LLlV59TDXmu7z9gatEoG2uy3"
        "10Pq8w5r3Wv5raLusdUuHyhiKCA0idtV3WG7CyULUeigpxxwrXcE2MxnoMOz6lPiI8FXkYXR"
        "urqu8D51xq5GA6n4mvqny8XngoGa3wvu8aBaVYdEPK6+X0CIgYgqrWwDJqkCcShPzFG2cDMT"
        "nAFy4A1gLXcC27iBjLhWxkQcUHXCNnGzelF9x1jcZZs/qfqjqfi0Oq0+WYu8APBKUNosxg6r"
        "k17t/W51n/c6oM56u9jsmDqnHqm5jsPkrQxTOAjkPMQ5VrCJW1nNadbTzxjrGAb2cj1VEmAV"
        "kBV44bIwvut4HfiZa9jJOBkTLGOcV1nFCLCdQSAF4AqagCgNBiYBScl5jB7e4yQX+ZuX6OQM"
        "3WxkOTeylU2ARADMhWkIOXi2VPtCXg49elupofL6nW9qnVDk4Hi9fAkZVeaAaSAl5ntOALNk"
        "xMG7wHc1jThUeIix+pQnpMRACyAJ8AGQkDSQ3ic1Q3HAXuFNoNrAdpcDUAEOM01aJ9aMhBG+"
        "qlVhfhqb/LWeh9rzbREP2CV+tOBff8GTZTbcUEpiRT0otqgHxL76bMyo7y4klKIWD2ros4r6"
        "odirVl0jfqlWnFOHjAo6aWTlVOx3Vq06ox4TX9RQsr4A4GPTYpQvpfVUXO0X4eovbvTrENFn"
        "/qWed3eJ/hcxUCyQXo94fgErnXKfHaXVs8heKOi91hnt9NBNBzs4zX5GOUke5uV/dyMkocYQ"
        "cYFzXAdASn7pjkwX0ycDImJSZjnCNLCMykLf/xXBfMvKleRMLb3g/wVoqZGHWt4mIwAAAABJ"
        "RU5ErkJggg=="
    ),
    ("white", 40): (
        "iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAQAAAAm93DmAAAEkUlEQVRIx42WW6gVZRTHfzOz"
        "T3pUjmh2TPKCcbQrmZcsC8EHE7IkiKiMClF6KAoKqSiIeqjsRlkZVi8qBV1ezMqiHipD66FQ"
        "0i5Y2YMolnYOlenx7D0zvx72t2fP2cet5/vYM7Nn1vxnrf9a6/99kQxrJGQk5JzWPB4GWAfw"
        "IPeSIdFprW03o3COxR7/MfVeR5Xut5kn9zABBKLwW04XCVdwfBgRDflGLOIoe4zERMQuN6qL"
        "rIiJlWATGQ/1N2phuUJKzApm8DuH+JzjdDOFtzibkYxkM7dQDXY5echC3t7DitjjWm8X8Vy3"
        "+KF9lkefX3i/k0Wc5jw7iyjCLMMl4uW+IJ7rI+LrASQ3MzM3Nw93Bnzee7zLa1zv7MGQg7k7"
        "37VGPmzsSnepqWkAaRxzU2sB9mw7HO06zy+YHwL4jJPFOW5yu3rCdiN3QH3fOXY7y2fLxRSX"
        "yIRDjOQq7uYOzuQ+RrTti4gO4Hqms4jv+Y0FJaSWQt6h6q/is1oEVx9pwaHqUd9V54qzvLbJ"
        "4+AMr1R1j2PFvWpWAqhf1wpG/xbXq5t94mRJicSz7FWPOEmc5N9FKjS1qr7nTwEyVXeI+Lna"
        "79RmWhqRJ8BqxgPfcgjooqvgJCehA9jPBjZTCZrzNgBfASN5KrRooTYRKWO4FYAD4X69jyUi"
        "ZivL6eYgh/gFyKhwmE1AxHJAbmI6WcAqSnpZKJT3RRzrn2pmrq4QcZmjfFytOqCuEfGyooRW"
        "hyzQTMiLar+618iKuEE9pq61y6vFN10pHlB1v53G4mtqzZr6aYPFZlF/plZN1aUinuMxVec5"
        "zYdc4yofcIYb1F4vFnG6tdCYur+hlfW4c6C7YO5JIOEgS+kHFnID8jMj6ONm5rOdC/iBDuBl"
        "KqRERMAEJtQTE4f8xJwBRMSkXMobZMA2LuQZxrKDG+ijwmz2cj8LOQzUeJrryKiE9zsZ09op"
        "O0N91Y8fOcvRIk4RJ7rIHkcE2RrrEreVyr4uGUEimhx+XAA2zvv92uN+XxK4H+3zO4+UbBp9"
        "c9RJZQ5jYE8QiHqZZ8gUFtDJaCpAwhnAFsYxlwnkZCSDZOUPjpQLW+CLZrUDCRE5NSAlBXIy"
        "4BOghsQluHpKd5KSYIPDSOz0QIscGAqiU4xMjMTdQ2zq3X1bo7AbHlboZwOQtegedDEaiMOT"
        "jcGj8qJU4U8+KN4tqc14e1s0MFd7HSfiRZ4lTnWgpEKqVfXRhn+terhKrZbMc/U/J4q428dE"
        "3DLoo6m6zxHNRaB1iX9LHRgE+K8TxW5P2Oc4cfGQ8rqqvO4N3c18qQ6U1rpjThGXqvqKiNtK"
        "MqurmuG2AtZ9TNyq5qWw5oqvBLauFM8zD//0zlMt9BQPnwwB1UzVS8RvAhU77fY++1X9wyWt"
        "cLbdLM13W+HhDl+yT82tFp5XfdVxg4NtB0gQWFzsO/7l0LHX55xZVMZpdl/N1pMcGM88LmYm"
        "XSxkAuvYxy52UQUqZCfdCNh+JiV+RnkwNFjds7jdW6fakWZkRCR0EJPTB5wAOohIW9pvmB4O"
        "7qIb/cTT7rDbc3iyETEM4/8Be4wBbIDzbdAAAAAASUVORK5CYII="
    ),
    ("white", 48): (
        "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"
    ),
}


def read_config():
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(CONFIG_FILE, encoding="utf-8")
    except configparser.Error as err:
        log.warning("Could not parse %s: %s", CONFIG_FILE, err)
    return parser


def get_setting(name, default=None):
    parser = read_config()
    if parser.has_option("settings", name):
        value = parser.get("settings", name).strip()
        if value:
            return value
    return default


def write_settings(**values):
    parser = read_config()
    if not parser.has_section("settings"):
        parser.add_section("settings")
    for name, value in values.items():
        parser.set("settings", name, value)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        parser.write(f)


def api_key():
    return get_setting("api_key")


def api_url():
    return get_setting("api_url", DEFAULT_API_URL)


def dashboard_url():
    url = api_url()
    marker = url.find("/api/")
    return url[:marker] if marker != -1 else url


def is_debug():
    return (get_setting("debug", "false") or "").lower() == "true"


def configure_logging():
    if log.handlers:
        return
    try:
        os.makedirs(RESOURCES_FOLDER, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if is_debug() else logging.INFO)
    log.propagate = False


def cli_os():
    return platform.system().lower()


def cli_arch():
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine.startswith("armv7") or machine == "arm":
        return "arm"
    if machine in ("i386", "i686", "x86"):
        return "386"
    return machine


def cli_binary_path():
    return os.path.join(
        RESOURCES_FOLDER, "wakatime-cli-{}-{}".format(cli_os(), cli_arch())
    )


def find_cli():
    candidates = [
        os.path.join(RESOURCES_FOLDER, "wakatime-cli"),
        cli_binary_path(),
        shutil.which("wakatime-cli"),
        shutil.which("wakatime"),
    ]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def download(url, destination):
    """Download url to destination, falling back to curl.

    python.org builds on macOS ship without CA certificates until the user runs
    "Install Certificates.command", so urllib can fail where curl succeeds.
    """
    try:
        with urllib.request.urlopen(url, timeout=CLI_TIMEOUT_SECONDS) as resp:
            with open(destination, "wb") as f:
                shutil.copyfileobj(resp, f)
        return
    except Exception as err:
        log.info("urllib download failed (%s), trying curl", err)
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("Could not download {} and curl is missing".format(url))
    subprocess.run(
        [curl, "-fsSL", "-o", destination, url],
        check=True,
        timeout=CLI_TIMEOUT_SECONDS * 5,
    )


def install_cli():
    os.makedirs(RESOURCES_FOLDER, exist_ok=True)
    url = CLI_DOWNLOAD_URL.format(os=cli_os(), arch=cli_arch())
    binary = cli_binary_path()
    log.info("Downloading wakatime-cli from %s", url)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "wakatime-cli.zip")
        download(url, archive)
        with zipfile.ZipFile(archive) as zf:
            member = os.path.basename(binary)
            with zf.open(member) as src, open(binary + ".tmp", "wb") as dst:
                shutil.copyfileobj(src, dst)
    os.chmod(binary + ".tmp", 0o755)
    os.replace(binary + ".tmp", binary)

    link = os.path.join(RESOURCES_FOLDER, "wakatime-cli")
    try:
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(binary, link)
    except OSError:
        shutil.copy2(binary, link)
        os.chmod(link, 0o755)
    log.info("Installed wakatime-cli at %s", binary)
    return binary


def ensure_cli():
    return find_cli() or install_cli()


def cli_supports(cli, flag):
    try:
        result = subprocess.run(
            [cli, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CLI_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return flag.encode() in result.stdout


def user_agent():
    return "idle/{} idle-hackatime/{}".format(platform.python_version(), __version__)


def heartbeat_args(heartbeat, supports_line_changes):
    entity = heartbeat["entity"]
    args = [
        "--entity", entity,
        "--entity-type", "file",
        "--category", "coding",
        "--plugin", user_agent(),
        "--time", "{:.6f}".format(heartbeat["time"]),
        "--lineno", str(heartbeat["lineno"]),
        "--cursorpos", str(heartbeat["cursorpos"]),
        "--lines-in-file", str(heartbeat["lines"]),
        "--alternate-project", os.path.basename(os.path.dirname(entity)),
        # Explicit true/false so wakatime-cli always includes is_write.
        "--write={}".format("true" if heartbeat["is_write"] else "false"),
    ]
    if entity.lower().endswith(PYTHON_EXTENSIONS):
        args += ["--alternate-language", "Python"]
    if supports_line_changes:
        # "=" form so negative values aren't read as flags.
        args.append("--human-line-changes={}".format(heartbeat["human_line_changes"]))
    return args


class HeartbeatSender:
    """Runs wakatime-cli off the Tk thread, one heartbeat at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._wakeup = threading.Condition(self._lock)
        self._queue = []
        self._cli = None
        self._supports_line_changes = False
        self._last_today_fetch = 0.0
        self.today_text = ""
        self._thread = threading.Thread(
            target=self._run, name="idle-hackatime", daemon=True
        )
        self._thread.start()

    def send(self, heartbeat):
        with self._lock:
            self._queue.append(heartbeat)
            self._wakeup.notify()

    def _run(self):
        try:
            self._cli = ensure_cli()
            self._supports_line_changes = cli_supports(
                self._cli, "--human-line-changes"
            )
            log.info(
                "Using %s (human line changes: %s)",
                self._cli,
                self._supports_line_changes,
            )
        except Exception:
            log.exception("Could not set up wakatime-cli")
            self.today_text = "wakatime-cli unavailable"
            return
        self._refresh_today()
        while True:
            with self._lock:
                while not self._queue:
                    if not self._wakeup.wait(timeout=TODAY_REFRESH_SECONDS):
                        break
                pending, self._queue = self._queue, []
            for heartbeat in pending:
                self._send_one(heartbeat)
            if pending or time.time() - self._last_today_fetch > TODAY_REFRESH_SECONDS:
                self._refresh_today()

    def _send_one(self, heartbeat):
        if not api_key():
            log.warning("No api_key in %s; heartbeat skipped", CONFIG_FILE)
            return
        cmd = [self._cli] + heartbeat_args(heartbeat, self._supports_line_changes)
        log.info("Sending heartbeat %s", json.dumps(heartbeat, sort_keys=True))
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as err:
            log.error("wakatime-cli failed to run: %s", err)
            return
        output = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode == 0:
            log.info("Heartbeat sent for %s", heartbeat["entity"])
        else:
            # Non-zero exits queue the heartbeat offline inside wakatime-cli.
            log.error("wakatime-cli exited %s: %s", result.returncode, output)

    def _refresh_today(self):
        self._last_today_fetch = time.time()
        if not api_key():
            self.today_text = "set API key in Options"
            return
        try:
            result = subprocess.run(
                [self._cli, "--today", "--plugin", user_agent()],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return
        text = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode == 0 and text:
            self.today_text = text


class ActivityTracker:
    def __init__(self, sender):
        self.sender = sender
        self.last_entity = None
        self.last_time = 0.0
        self.line_changes = {}

    def record_line_changes(self, entity, delta):
        self.line_changes[entity] = self.line_changes.get(entity, 0) + delta

    def handle(self, entity, lineno, cursorpos, lines, is_write):
        now = time.time()
        due = (
            is_write
            or entity != self.last_entity
            or now - self.last_time >= HEARTBEAT_INTERVAL_SECONDS
        )
        if not due or not api_key():
            return
        self.last_entity = entity
        self.last_time = now
        self.sender.send(
            {
                "entity": entity,
                "time": now,
                "is_write": is_write,
                "lineno": lineno,
                "cursorpos": cursorpos,
                "lines": lines,
                "human_line_changes": self.line_changes.pop(entity, 0),
            }
        )


_tracker = None


def tracker():
    global _tracker
    if _tracker is None:
        configure_logging()
        _tracker = ActivityTracker(HeartbeatSender())
    return _tracker


try:
    from idlelib.delegator import Delegator
except ImportError:  # Running the installer without idlelib.
    Delegator = object


def logo_image(label):
    """Return the logo sized to the label's font and coloured like its text."""
    from tkinter import PhotoImage, TclError, font
    from tkinter.ttk import Style

    style = Style(label)
    spec = label.cget("font") or style.lookup("TLabel", "font") or "TkDefaultFont"
    linespace = font.Font(root=label, font=spec).metrics("linespace")
    sizes = sorted({size for _, size in LOGO_PNG})
    size = min(sizes, key=lambda s: abs(s - linespace))

    foreground = str(label.cget("foreground")) or style.lookup("TLabel", "foreground") or "black"
    red, green, blue = label.winfo_rgb(foreground)
    colour = "white" if (0.299 * red + 0.587 * green + 0.114 * blue) / 65535 > 0.5 else "black"
    if "nsimage" in label.tk.splitlist(label.tk.call("image", "types")):
        try:
            return retina_logo(label, colour, size)
        except (OSError, KeyError, TclError) as err:
            log.info("Retina logo unavailable (%s), using PhotoImage", err)
    try:
        return PhotoImage(master=label, data=LOGO_PNG[colour, size], format="png")
    except TclError:
        return None


def retina_logo(label, colour, size):
    """Draw the 2x PNG at `size` points with Tk 9's macOS nsimage, so it stays sharp on Retina.

    nsimage only reads from a file, so the PNG is written under ~/.wakatime.
    """
    name = "hackatime-logo-{}-{}".format(colour, size)
    if name in label.tk.splitlist(label.tk.call("image", "names")):
        return name
    png = base64.b64decode(LOGO_PNG[colour, size * 2])
    path = os.path.join(RESOURCES_FOLDER, "idle-{}.png".format(name))
    if not os.path.exists(path) or open(path, "rb").read() != png:
        os.makedirs(RESOURCES_FOLDER, exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
    label.tk.call(
        "image", "create", "nsimage", name,
        "-source", path, "-as", "file", "-width", size, "-height", size,
    )
    return name


def ask_api_key(parent, initial):
    """Modal prompt for the API key; returns the stripped key, or None if cancelled.

    simpledialog.askstring fails on Tk 9.1 with Python 3.14 and older, which still
    call the removed ::tk::unsupported::MacWindowStyle command.
    """
    import tkinter as tk
    from tkinter import ttk

    result = []
    top = tk.Toplevel(parent)
    top.title("Hackatime API Key")
    top.transient(parent)
    top.resizable(False, False)

    frame = ttk.Frame(top, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame,
        text="Paste your Hackatime API key.\nFind it at {}/my/settings".format(dashboard_url()),
    ).pack(anchor="w")
    value = tk.StringVar(top, initial)
    entry = ttk.Entry(frame, textvariable=value, width=40)
    entry.pack(fill="x", pady=(8, 12))

    def ok(event=None):
        if value.get().strip():
            result.append(value.get().strip())
        top.destroy()

    def cancel(event=None):
        top.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e")
    ttk.Button(buttons, text="OK", command=ok, default="active").pack(side="right")
    ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right", padx=(0, 6))
    top.bind("<Return>", ok)
    top.bind("<KP_Enter>", ok)
    top.bind("<Escape>", cancel)
    top.protocol("WM_DELETE_WINDOW", cancel)

    top.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - top.winfo_reqheight()) // 3
    top.geometry("+{}+{}".format(max(x, 0), max(y, 0)))
    entry.focus_set()
    entry.select_range(0, "end")
    top.wait_visibility()
    top.grab_set()
    top.wait_window()
    return result[0] if result else None


class _ChangeFilter(Delegator):
    """Percolator filter that observes every insert and delete in the text."""

    def __init__(self, extension):
        Delegator.__init__(self)
        self.extension = extension

    def insert(self, index, chars, tags=None):
        self.delegate.insert(index, chars, tags)
        self.extension.on_text_change(chars.count("\n"))

    def delete(self, index1, index2=None):
        text = self.extension.text
        end = index2 if index2 is not None else index1 + "+1c"
        removed = text.get(index1, end).count("\n")
        self.delegate.delete(index1, index2)
        self.extension.on_text_change(-removed)


class IdleHackatime:
    """IDLE extension entry point, created once per editor window."""

    menudefs = [
        (
            "options",
            [
                None,
                ("Hackatime API _Key...", "<<hackatime-api-key>>"),
                ("Hackatime _Dashboard", "<<hackatime-dashboard>>"),
            ],
        )
    ]

    def __init__(self, editwin):
        self.editwin = editwin
        self.text = editwin.text
        self.tracker = tracker()
        self._activity_job = None
        self._status_job = None
        self._logo = self._add_status_label()

        self.filter = _ChangeFilter(self)
        editwin.per.insertfilter(self.filter)

        io = editwin.io
        original_writefile = io.writefile

        def writefile(filename):
            # Read the cursor first: IDLE may append a final newline while
            # writing, which moves the insert mark to a new empty line.
            lineno, cursorpos = self.cursor()
            ok = original_writefile(filename)
            if ok:
                self.on_write(filename, lineno, cursorpos)
            return ok

        io.writefile = writefile

        self.text.bind("<<hackatime-api-key>>", self.api_key_event)
        self.text.bind("<<hackatime-dashboard>>", self.dashboard_event)
        for sequence in ("<KeyRelease>", "<ButtonRelease>", "<FocusIn>"):
            self.text.bind(sequence, self.on_activity, add="+")

        self._refresh_status()
        if not api_key():
            self.text.after(500, self._prompt_for_missing_key)

    def filename(self):
        name = self.editwin.io.filename if self.editwin.io else None
        return os.path.realpath(name) if name else None

    def cursor(self):
        line, column = self.text.index("insert").split(".")
        return int(line), int(column) + 1

    def line_count(self):
        return int(self.text.index("end-1c").split(".")[0])

    def _heartbeat(self, entity, is_write, lineno=None, cursorpos=None):
        if lineno is None:
            lineno, cursorpos = self.cursor()
        self.tracker.handle(entity, lineno, cursorpos, self.line_count(), is_write)

    def on_text_change(self, line_delta):
        entity = self.filename()
        if not entity:
            return
        if line_delta:
            self.tracker.record_line_changes(entity, line_delta)
        self._schedule_activity()

    def on_activity(self, event=None):
        self._schedule_activity()

    def _schedule_activity(self):
        # Coalesce bursts of events and read the cursor once Tk has settled.
        if self._activity_job is None:
            self._activity_job = self.text.after_idle(self._flush_activity)

    def _flush_activity(self):
        self._activity_job = None
        entity = self.filename()
        if entity:
            self._heartbeat(entity, is_write=False)

    def on_write(self, filename, lineno, cursorpos):
        self._heartbeat(os.path.realpath(filename), True, lineno, cursorpos)

    def api_key_event(self, event=None):
        key = ask_api_key(self.editwin.top, api_key() or "")
        if key:
            write_settings(api_key=key, api_url=api_url())
            self.tracker.sender._last_today_fetch = 0.0
        return "break"

    def dashboard_event(self, event=None):
        webbrowser.open(dashboard_url())
        return "break"

    def _prompt_for_missing_key(self):
        global _prompted_for_key
        if _prompted_for_key or api_key():
            return
        _prompted_for_key = True
        self.api_key_event()

    def _add_status_label(self):
        self.editwin.status_bar.set_label("hackatime")
        label = self.editwin.status_bar.labels["hackatime"]
        logo = logo_image(label)
        if logo is not None:
            from tkinter.ttk import Style

            Style(label).configure("Hackatime.TLabel", space=2)
            # Clear the rounded window corner and the separator above the status bar.
            label.configure(
                image=logo, compound="left", padding=(4, 2, 0, 1), style="Hackatime.TLabel"
            )
        return logo

    def _refresh_status(self):
        text = self.tracker.sender.today_text
        if text:
            prefix = "" if self._logo is not None else "Hackatime: "
            self.editwin.status_bar.set_label("hackatime", prefix + text)
        self._status_job = self.text.after(STATUS_REFRESH_MS, self._refresh_status)

    def close(self):
        # IDLE calls this before destroying the window, so the jobs can still be cancelled.
        for job in (self._activity_job, self._status_job):
            if job is not None:
                self.text.after_cancel(job)
        if self.editwin.per is not None:
            self.editwin.per.removefilter(self.filter)


_prompted_for_key = False


def install_dir():
    if site.ENABLE_USER_SITE:
        return site.getusersitepackages()
    return sysconfig.get_paths()["purelib"]


def read_idle_config():
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(IDLE_CONFIG_FILE, encoding="utf-8")
    return parser


def write_idle_config(parser):
    os.makedirs(os.path.dirname(IDLE_CONFIG_FILE), exist_ok=True)
    with open(IDLE_CONFIG_FILE, "w", encoding="utf-8") as f:
        parser.write(f)


def install(argv):
    source = os.path.abspath(__file__)
    target_dir = install_dir()
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(source))
    if os.path.abspath(target) != source:
        shutil.copyfile(source, target)
    print("Installed {} to {}".format(EXTENSION_NAME, target))

    parser = read_idle_config()
    if not parser.has_section(EXTENSION_NAME):
        parser.add_section(EXTENSION_NAME)
    parser.set(EXTENSION_NAME, "enable", "True")
    parser.set(EXTENSION_NAME, "enable_editor", "True")
    parser.set(EXTENSION_NAME, "enable_shell", "False")
    write_idle_config(parser)
    print("Enabled the extension in {}".format(IDLE_CONFIG_FILE))

    configure_logging()
    print("wakatime-cli: {}".format(ensure_cli()))

    key = os.environ.get("HACKATIME_API_KEY") or api_key()
    if not key and sys.stdin.isatty():
        key = input("Hackatime API key (from {}/my/settings): ".format(
            dashboard_url())).strip()
    if key:
        write_settings(api_key=key, api_url=api_url())
        print("Saved API key to {}".format(CONFIG_FILE))
    else:
        print("No API key yet. IDLE will ask for it on start.")

    print("Done. Restart IDLE with: {} -m idlelib".format(sys.executable))


def uninstall(argv):
    target = os.path.join(install_dir(), "IdleHackatime.py")
    if os.path.exists(target):
        os.remove(target)
        print("Removed {}".format(target))
    parser = read_idle_config()
    if parser.remove_section(EXTENSION_NAME):
        write_idle_config(parser)
        print("Disabled the extension in {}".format(IDLE_CONFIG_FILE))


def main(argv):
    commands = {"install": install, "uninstall": uninstall}
    if len(argv) < 2 or argv[1] not in commands:
        print("usage: {} {{install,uninstall}}".format(os.path.basename(argv[0])))
        return 2
    commands[argv[1]](argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
