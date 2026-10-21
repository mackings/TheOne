"""Enrolment phrases per language. Phrases are phonetically varied and avoid
digits so that the template generalises to free speech (text-independent)."""
from __future__ import annotations

import random

LANGUAGES = {
    "en": "English",
    "pcm": "Nigerian Pidgin",
    "yo": "Yorùbá",
    "ha": "Hausa",
    "ig": "Igbo",
}

PHRASES: dict[str, list[str]] = {
    "en": [
        "My voice is my password and I am enrolling it with my bank today.",
        "The quick brown fox jumps over the lazy dog near the river bank.",
        "Please confirm that this is my account and that I am speaking freely.",
        "I usually check my balance in the morning before going to work.",
        "Sunlight through the window makes the whole room feel warm and bright.",
    ],
    "pcm": [
        "Na my voice be my password and I dey register am with my bank today.",
        "I dey check my account balance for morning before I go work.",
        "Abeg confirm say na me get this account and I dey talk by myself.",
        "Rain fall yesterday evening and the road for my area flood small.",
        "I wan make my money safe so I dey do this voice registration now.",
    ],
    "yo": [
        "Ohùn mi ni ọ̀rọ̀ ìpamọ́ mi, mo sì ń forúkọ sílẹ̀ pẹ̀lú báńkì mi lónìí.",
        "Mo máa ń yẹ owó tó wà nínú àkàǹtì mi wò ní àárọ̀ kí n tó lọ sí iṣẹ́.",
        "Jọ̀wọ́ jẹ́rìí pé àkàǹtì tèmi nìyí àti pé èmi fúnra mi ni mo ń sọ̀rọ̀.",
        "Òjò rọ̀ lálẹ́ àná, ojú ọ̀nà sì tutù ní àgbègbè wa.",
        "Mo fẹ́ kí owó mi wà láìléwu, ìdí nìyí tí mo fi ń forúkọ ohùn mi sílẹ̀.",
    ],
    "ha": [
        "Muryata ita ce kalmar sirrina, kuma ina yin rajista da bankina a yau.",
        "Nakan duba ma'aunin asusuna da safe kafin in tafi wurin aiki.",
        "Don Allah ka tabbatar cewa wannan asusu nawa ne kuma ni ne nake magana.",
        "An yi ruwa jiya da yamma, hanyoyin unguwarmu sun yi laka.",
        "Ina son kudina su kasance cikin aminci, shi ya sa nake yin rajistar murya.",
    ],
    "ig": [
        "Olu m bụ okwu nzuzo m, ana m edebanye ya na ụlọ akụ m taa.",
        "Ana m elele ego dị n'akaụntụ m n'ụtụtụ tupu m aga ọrụ.",
        "Biko kwenye na akaụntụ a bụ nke m na ọ bụ m n'onwe m na-ekwu okwu.",
        "Mmiri zoro n'abalị ụnyaahụ, okporo ụzọ anyị wee jupụta na mmiri.",
        "Achọrọ m ka ego m dị na nchebe, ya mere m ji edebanye olu m ugbu a.",
    ],
}

GUIDE: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Hello {name}. I will guide you through registering your voice. Find a quiet spot and speak naturally.",
        "step": "Step {n} of {total}. Please read this sentence aloud:",
        "retry": "Let's try that one again. {issue}",
        "done": "Thank you {name}. Your voice has been registered securely.",
    },
    "pcm": {
        "welcome": "How far {name}. I go guide you to register your voice. Find quiet place and talk as you dey talk normally.",
        "step": "Step {n} of {total}. Abeg read this sentence out loud:",
        "retry": "Make we try am again. {issue}",
        "done": "Thank you {name}. We don register your voice safely.",
    },
    "yo": {
        "welcome": "Ẹ káàbọ̀ {name}. Màá tọ́ ọ sọ́nà láti forúkọ ohùn rẹ sílẹ̀. Wá ibi tó dákẹ́ kí o sì sọ̀rọ̀ bí o ṣe máa ń sọ.",
        "step": "Ìgbésẹ̀ {n} nínú {total}. Jọ̀wọ́ ka gbólóhùn yìí sókè:",
        "retry": "Ẹ jẹ́ ká tún gbìyànjú. {issue}",
        "done": "Ẹ ṣeun {name}. A ti forúkọ ohùn rẹ sílẹ̀ láìléwu.",
    },
    "ha": {
        "welcome": "Sannu {name}. Zan jagorance ka wajen yin rajistar muryarka. Nemi wuri mai shiru ka yi magana kamar yadda ka saba.",
        "step": "Mataki na {n} cikin {total}. Don Allah ka karanta wannan jumla da ƙarfi:",
        "retry": "Mu sake gwadawa. {issue}",
        "done": "Na gode {name}. An yi rajistar muryarka cikin aminci.",
    },
    "ig": {
        "welcome": "Ndewo {name}. Aga m eduzi gị idebanye olu gị. Chọta ebe dị jụụ ma kwuo okwu dị ka ị na-ekwu.",
        "step": "Nzọụkwụ {n} nke {total}. Biko gụpụta ahịrịokwu a:",
        "retry": "Ka anyị nwaa ọzọ. {issue}",
        "done": "Daalụ {name}. Edebanyela olu gị n'enweghị nsogbu.",
    },
}


def pick_phrases(language: str, n: int, seed: int | None = None) -> list[str]:
    pool = PHRASES.get(language) or PHRASES["en"]
    rng = random.Random(seed)
    return rng.sample(pool, k=min(n, len(pool)))


def guide(language: str) -> dict[str, str]:
    return GUIDE.get(language) or GUIDE["en"]
