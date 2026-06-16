"""Curated starter knowledge for Dost — Indian/South-Asian culture + US-diaspora practicalities.

These short, factual articles seed the knowledge base so Dost answers culture/festival and
practical questions ("how is Pongal celebrated?", "what's an H-1B?") with grounded, India-tuned
context instead of generic web text. General & educational only — the immigration/tax notes say
plainly to consult a professional for specifics. Idempotent: re-seeding re-embeds only what changed.

Add more by appending to ARTICLES (slug, title, vertical, text) — no code change.
"""

from __future__ import annotations

from typing import Any

_DISCLAIMER = (" This is general information, not legal or tax advice — rules change and every case "
               "differs, so confirm specifics with a qualified professional.")

# (slug, title, vertical, text). vertical=None = general/cross-vertical knowledge.
ARTICLES: list[dict[str, Any]] = [
    {"slug": "diwali", "title": "Diwali (Deepavali): the festival of lights", "vertical": None,
     "text": "Diwali, or Deepavali, is the most widely celebrated Indian festival — a five-day "
             "'festival of lights' usually in October or November. Homes are cleaned and decorated "
             "with diyas (oil lamps), rangoli, and string lights; families perform Lakshmi puja for "
             "prosperity, share sweets (mithai) like ladoo and barfi, wear new clothes, exchange "
             "gifts, and light fireworks. It symbolizes the victory of light over darkness and good "
             "over evil. In the US, temples and Indian associations hold large Diwali melas and "
             "cultural programs, and sweet shops and grocers stock special boxes for the season."},
    {"slug": "holi", "title": "Holi: the festival of colors", "vertical": None,
     "text": "Holi is the spring 'festival of colors,' celebrated in March. People throw colored "
             "powder (gulal) and water, dance to music, and share festive foods like gujiya and "
             "thandai. The night before, Holika Dahan bonfires mark the triumph of good over evil. "
             "It is joyful and informal — a celebration of renewal, forgiveness, and community. In "
             "the US, Holi color events are hosted by temples, universities, and Indian groups, "
             "often in parks, and are popular with people of all backgrounds."},
    {"slug": "navratri-garba", "title": "Navratri, Garba & Dussehra", "vertical": None,
     "text": "Navratri is nine nights honoring the goddess Durga, celebrated especially by Gujarati "
             "communities with Garba and Dandiya-Raas — circular folk dances done in colorful "
             "traditional dress to live or recorded music. It usually falls in September or October "
             "and ends with Dussehra (Vijayadashami), marking the victory of good over evil. In the "
             "US, large Garba nights are organized by Gujarati Samaj and temples and can draw "
             "thousands; many sell tickets and feature well-known singers."},
    {"slug": "pongal-sankranti", "title": "Pongal & Makar Sankranti (harvest)", "vertical": None,
     "text": "Pongal (Tamil) and Makar Sankranti (across much of India) are mid-January harvest "
             "festivals thanking the sun and nature. Pongal is a four-day Tamil festival; the dish "
             "'pongal' — rice boiled with milk and jaggery — is cooked until it overflows, a sign of "
             "abundance. Sankranti is marked by kite-flying, sesame-jaggery sweets (til), and bonfires "
             "(Lohri in Punjab). Tamil and Telugu associations in the US hold Pongal/Sankranti events "
             "with food, music, and rangoli (muggu/kolam) competitions."},
    {"slug": "onam", "title": "Onam (Kerala's harvest festival)", "vertical": None,
     "text": "Onam is Kerala's grand harvest festival (August–September), celebrating the legendary "
             "return of King Mahabali. Highlights are the elaborate flower carpet (pookalam), the "
             "multi-course vegetarian feast Onam Sadhya served on a banana leaf, traditional dress "
             "(kasavu sarees and mundu), and folk arts. Malayalee associations across the US host "
             "Onam Sadhyas and cultural programs that are open to the community."},
    {"slug": "ugadi", "title": "Ugadi & Gudi Padwa (New Year)", "vertical": None,
     "text": "Ugadi (Telugu and Kannada) and Gudi Padwa (Marathi) mark the lunar new year, usually "
             "in March or April. A signature of Ugadi is 'Ugadi pachadi,' a dish blending six tastes "
             "— sweet, sour, salty, bitter, tangy, and spicy — to represent that the year ahead holds "
             "all of life's flavors. Families read the new year's panchangam (almanac). Telugu, "
             "Kannada, and Marathi associations in the US hold New Year cultural events."},
    {"slug": "raksha-bandhan", "title": "Raksha Bandhan", "vertical": None,
     "text": "Raksha Bandhan (August) celebrates the bond between siblings. A sister ties a decorative "
             "thread (rakhi) on her brother's wrist for his well-being, and he gives a gift and a "
             "promise of protection. Families share sweets. In the US, the day is often marked at "
             "home, with rakhis mailed between India and America ahead of time; Indian grocers and "
             "gift shops carry rakhi sets in the weeks before."},
    {"slug": "ganesh-chaturthi", "title": "Ganesh Chaturthi", "vertical": None,
     "text": "Ganesh Chaturthi (August–September) honors Lord Ganesha, the remover of obstacles. "
             "Clay idols are installed at home or in community pandals, worshipped for one to ten "
             "days with modak (a sweet dumpling Ganesha loves), and then immersed in water "
             "(visarjan). In the US, temples and Maharashtrian and other associations host Ganesh "
             "celebrations, often using eco-friendly idols and arranged immersion."},
    {"slug": "temple-etiquette", "title": "Visiting a Hindu temple: what to expect", "vertical": "temples",
     "text": "Hindu temples (mandirs) in the US welcome visitors of all backgrounds. Remove your "
             "shoes before entering the prayer hall (there are usually shoe racks), dress modestly, "
             "and keep phones silent. You may receive a bit of prasad (blessed food) or vibhuti/"
             "kumkum; it's fine to accept with your right hand. You don't need to know the rituals — "
             "observing quietly is respectful. Many temples list aarti and darshan timings online and "
             "have a community hall, bookstore, and canteen. Sikh gurdwaras similarly ask visitors to "
             "remove shoes and cover their heads, and serve a free community meal (langar) to all."},
    {"slug": "h1b-basics", "title": "H-1B visa basics (general info)", "vertical": "legal",
     "text": "The H-1B is a US work visa for 'specialty occupations' that typically require at least "
             "a bachelor's degree; it's widely used by Indian tech and other professionals. A US "
             "employer sponsors and petitions for the worker. New H-1Bs are subject to an annual cap "
             "and a lottery (cap-exempt employers like universities are an exception). It's normally "
             "granted for three years, extendable to six, and can be a step toward a green card. "
             "Spouses hold H-4 status and may work only if eligible for an H-4 EAD." + _DISCLAIMER},
    {"slug": "green-card-basics", "title": "Green card / permanent residency basics", "vertical": "legal",
     "text": "A green card grants lawful permanent residence in the US. Common routes for Indians are "
             "employment-based (EB-1/EB-2/EB-3, usually after a labor certification and an employer "
             "petition) and family-based sponsorship. Because of per-country limits and high demand, "
             "employment-based green-card waits for India can be very long. The process generally "
             "moves through a petition, a priority date that must become 'current,' and then "
             "adjustment of status or consular processing." + _DISCLAIMER},
    {"slug": "f1-opt", "title": "F-1 students, OPT & STEM OPT (general info)", "vertical": "legal",
     "text": "The F-1 visa is for international students. After graduating, many use Optional "
             "Practical Training (OPT) to work in their field for up to 12 months; graduates of "
             "eligible STEM degrees can apply for a 24-month STEM OPT extension. Work must relate to "
             "the field of study, and students apply through their school's international office (DSO) "
             "and USCIS. Many later move to H-1B or other statuses." + _DISCLAIMER},
    {"slug": "taxes-nri", "title": "US taxes for Indians & newcomers (general info)", "vertical": "finance",
     "text": "Most people working in the US file a federal tax return each year (typically by mid-"
             "April), plus state returns where applicable. Your residency status for tax (resident vs "
             "non-resident alien, often determined by the substantial-presence test) affects which "
             "forms you file and how worldwide income is treated. People on visas without a Social "
             "Security Number may need an ITIN. India and the US have a tax treaty, and foreign "
             "accounts can carry reporting requirements (e.g. FBAR). A CPA familiar with immigrant "
             "filers can help." + _DISCLAIMER},
    {"slug": "money-to-india", "title": "Sending money to India (remittances)", "vertical": "finance",
     "text": "Indians in the US commonly remit money home using bank wire transfers or specialized "
             "remittance services and apps. Compare the exchange rate, transfer fee, and delivery "
             "speed — the headline 'no fee' is not always the best total once the rate is included. "
             "Keep records, and be aware that large or frequent transfers may have reporting "
             "considerations on either side." + _DISCLAIMER},
    {"slug": "new-to-usa", "title": "New to the US? Finding Indian groceries, food & community",
     "vertical": None,
     "text": "Settling in is easier once you find your community. Indian grocery stores (Patel "
             "Brothers and many local desi stores) carry spices, lentils, atta, fresh produce, and "
             "frozen favorites; many metros also have South Indian, Gujarati, Punjabi, and other "
             "regional restaurants, sweet shops, and tiffin/catering services. Temples and regional "
             "associations (Telugu, Tamil, Gujarati, Bengali, Marathi and more) host festivals and "
             "are a great way to meet people. Use Dost to find these near you, and add ones you love "
             "so others can find them too."},
]


def seed() -> dict[str, Any]:
    """Upsert the curated articles into the knowledge base (idempotent)."""
    from . import knowledge
    added = unchanged = 0
    for a in ARTICLES:
        res = knowledge.upsert_document(
            source_type="article", source_ref=a["slug"], content=a["text"],
            vertical=a.get("vertical"), title=a["title"])
        if res.get("unchanged"):
            unchanged += 1
        elif res.get("ok"):
            added += 1
    return {"articles": len(ARTICLES), "indexed": added, "unchanged": unchanged}
