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

    # --- more festivals ---
    {"slug": "janmashtami", "title": "Krishna Janmashtami", "vertical": None,
     "text": "Krishna Janmashtami (August–September) celebrates the birth of Lord Krishna. Devotees "
             "often fast until midnight — Krishna's birth hour — sing bhajans, decorate a cradle for "
             "the infant Krishna, and offer butter and milk sweets he loved. In Maharashtra, 'Dahi "
             "Handi' teams form human pyramids to break a high pot of curd. US temples, especially "
             "ISKCON and many mandirs, hold midnight aarti, abhishekam, and cultural programs."},
    {"slug": "durga-puja", "title": "Durga Puja (Bengali)", "vertical": None,
     "text": "Durga Puja (September–October) is the grandest festival for Bengalis, honoring goddess "
             "Durga's victory over the demon Mahishasura. Elaborate idols are installed in decorated "
             "pandals and worshipped over five days with dhak drumming, dhunuchi dance, Bengali food "
             "(bhog, khichuri, mishti) and new clothes, ending with immersion (visarjan) and Sindoor "
             "Khela. Bengali associations across the US host large community Pujas open to everyone."},
    {"slug": "gurpurab", "title": "Gurpurab (Guru Nanak Jayanti)", "vertical": None,
     "text": "Gurpurab, usually Guru Nanak Gurpurab in November, marks the birth of Guru Nanak, the "
             "founder of Sikhism. Observances include an Akhand Path (continuous reading of the Guru "
             "Granth Sahib), Nagar Kirtan processions, hymn-singing (kirtan), and langar — a free "
             "community meal served to all. US gurdwaras warmly welcome visitors of every background; "
             "cover your head, remove your shoes, and you're invited to share in langar."},
    {"slug": "baisakhi", "title": "Baisakhi / Vaisakhi", "vertical": None,
     "text": "Baisakhi (around April 13–14) is the Punjabi harvest festival and Sikh new year, and "
             "marks the founding of the Khalsa in 1699. It's celebrated with energetic Bhangra and "
             "Gidda dancing, dhol drumming, fairs, and festive food. US gurdwaras and Punjabi "
             "associations hold Nagar Kirtans, kirtan, and community meals — a colorful, joyful day."},
    {"slug": "karva-chauth", "title": "Karva Chauth", "vertical": None,
     "text": "Karva Chauth (October–November) is a day when married women — and increasingly some "
             "husbands too — fast from sunrise until they sight the moon, praying for their spouse's "
             "well-being. The day includes henna (mehndi), festive dress, a pre-dawn meal (sargi), "
             "and breaking the fast after viewing the moon, often through a sieve. It's widely "
             "observed in North Indian communities across the US, frequently as group gatherings."},

    # --- culture & food ---
    {"slug": "indian-wedding", "title": "What to expect at an Indian wedding", "vertical": None,
     "text": "Indian weddings in the US are often multi-day, vibrant celebrations. Common events "
             "include a mehndi (henna) night, a sangeet (music and dance), a haldi (turmeric) "
             "ceremony, the wedding itself (e.g. a Hindu ceremony around a sacred fire, or an Anand "
             "Karaj in a gurdwara), and a reception. Guests wear bright traditional clothes (avoid "
             "white or black for Hindu ceremonies) and giving cash ('shagun') is customary. Expect "
             "abundant food, family, dancing — and ceremonies that may run on a relaxed schedule."},
    {"slug": "vegetarian-jain-dining", "title": "Vegetarian, vegan & Jain dining", "vertical": "restaurants",
     "text": "Indian food serves vegetarians and vegans well — most US Indian restaurants mark veg "
             "dishes clearly, and many South Indian and Gujarati places are fully vegetarian ('pure "
             "veg' means a kitchen with no meat). For Jain food (no onion, garlic, or root "
             "vegetables), call ahead: many restaurants and caterers can prepare Jain versions, and "
             "some menus label them. Indian grocers also stock plenty of veg and Jain-friendly "
             "products. Use Dost's dietary filters to find veg, vegan, and Jain options near you."},

    # --- immigration (general info) ---
    {"slug": "h4-ead", "title": "H-4 spouses & the H-4 EAD (general info)", "vertical": "legal",
     "text": "H-4 status is for the spouse and children of an H-1B worker. H-4 spouses cannot work "
             "automatically, but may apply for an H-4 EAD (work permit) if the H-1B spouse has an "
             "approved I-140 immigrant petition, or has H-1B time extended beyond six years under "
             "AC21. With a valid H-4 EAD, the spouse can work for any employer. Children on H-4 "
             "generally cannot work and may 'age out' at 21." + _DISCLAIMER},
    {"slug": "us-citizenship", "title": "Becoming a US citizen (naturalization)", "vertical": "legal",
     "text": "Naturalization is how a green-card holder becomes a US citizen, via Form N-400. Most "
             "can apply after five years as a permanent resident — or three years if married to and "
             "living with a US citizen — if they meet continuous-residence, physical-presence, and "
             "good-moral-character requirements. The process includes biometrics, an interview, and "
             "English and US civics tests, ending with the Oath of Allegiance. India doesn't allow "
             "dual citizenship, so new US citizens usually apply for an OCI card." + _DISCLAIMER},
    {"slug": "visa-stamping-india", "title": "US visa stamping in India (general info)", "vertical": "legal",
     "text": "Visa 'stamping' is getting the physical visa in your passport at a US consulate, needed "
             "to re-enter the US after travel — an I-797 approval alone isn't a visa. In India, US "
             "consulates are in Mumbai, New Delhi, Chennai, Kolkata, and Hyderabad. Many H-1B/H-4 "
             "renewals qualify for the interview-waiver 'dropbox' if the prior visa is recent; others "
             "need an in-person interview. Wait times vary, so plan India trips around stamping "
             "timelines." + _DISCLAIMER},

    # --- settling in: money & ID ---
    {"slug": "ssn-stateid", "title": "Social Security Number & state ID", "vertical": None,
     "text": "A Social Security Number (SSN) is issued by the Social Security Administration to people "
             "authorized to work; you'll need it for jobs, banking, and credit, so apply soon after "
             "your work authorization is active. For everyday ID and driving, get a state driver's "
             "license or non-driver state ID at the DMV — requirements vary by state but usually "
             "include your passport, visa, I-94, and proof of address. Keep your SSN card secure and "
             "don't carry it around."},
    {"slug": "building-credit", "title": "Building US credit from scratch", "vertical": "finance",
     "text": "New immigrants usually arrive with no US credit history, which affects renting, loans, "
             "and some cards. Build credit with a secured card or a newcomer card (some issuers "
             "accept applicants without an SSN or prior history), by becoming an authorized user on a "
             "trusted person's card, and by always paying on time and keeping balances low. A few "
             "services can import your Indian credit history. Over several months, an on-time record "
             "builds a solid score." + _DISCLAIMER},
    {"slug": "us-banking", "title": "Opening a US bank account", "vertical": "finance",
     "text": "You can usually open a US checking and savings account with your passport, visa, and a "
             "US address; some banks let you open one before your SSN arrives. A checking account "
             "with a debit card covers daily spending, while a credit card used responsibly builds "
             "credit. Watch for monthly fees (often waived with direct deposit or a minimum balance), "
             "and use the bank's app for transfers, bill pay, and Zelle. Big banks and credit unions "
             "have branches in most Indian-heavy metros."},
    {"slug": "health-insurance", "title": "US health insurance basics", "vertical": "finance",
     "text": "US healthcare is expensive without insurance, so don't go uninsured. Most employees get "
             "coverage through their employer (with an annual 'open enrollment'); others buy a plan "
             "on the ACA marketplace or through a broker. Learn the basics — premium (monthly cost), "
             "deductible (what you pay before coverage kicks in), copay/coinsurance, and in-network "
             "vs out-of-network providers. People between jobs sometimes buy short-term or visitor "
             "plans to bridge a gap." + _DISCLAIMER},
    {"slug": "retirement-401k", "title": "401(k) & IRA retirement basics", "vertical": "finance",
     "text": "The US has tax-advantaged retirement accounts. A 401(k) is offered by many employers — "
             "contributions come from your paycheck pre-tax (or Roth/after-tax), and employers often "
             "'match' part of it, which is essentially free money worth capturing. Individuals can "
             "also open an IRA (traditional or Roth). Even if you might return to India, employer "
             "matches and compounding can be valuable; understand vesting and withdrawal rules "
             "first." + _DISCLAIMER},
    {"slug": "fbar-foreign-accounts", "title": "Reporting Indian accounts (FBAR/FATCA)", "vertical": "finance",
     "text": "US tax residents (citizens, green-card holders, and many visa holders) generally must "
             "report foreign financial accounts. If your non-US accounts — including Indian savings, "
             "NRE/NRO, fixed deposits, and some investments — together exceed $10,000 at any point in "
             "the year, you typically must file an FBAR (FinCEN Form 114). Larger holdings may also "
             "trigger FATCA reporting (Form 8938). Penalties for not filing can be steep, so track "
             "your Indian accounts and tell your tax preparer." + _DISCLAIMER},

    # --- community ---
    {"slug": "indian-community-associations", "title": "Finding Indian community & associations",
     "vertical": None,
     "text": "Across the US, regional and linguistic associations help Indians stay connected — "
             "Telugu (TANA/ATA), Tamil sangams, Gujarati Samaj, Bengali associations, Maharashtra "
             "Mandals, Kannada Koota, Malayalee associations, Punjabi groups, plus pan-Indian and "
             "alumni (IIT/NIT) networks. They run festivals, cultural programs, language classes, and "
             "networking, and are a welcoming first step in a new city. Temples and gurdwaras are "
             "community hubs too. Use Dost to find temples, groups, and events near you."},
    {"slug": "raising-kids-heritage", "title": "Raising kids with Indian culture", "vertical": None,
     "text": "Many Indian-American parents want their children to keep the language and culture. "
             "Options include weekend heritage-language and cultural schools (Telugu, Tamil, Hindi, "
             "Balvihar, Gujarati or Bengali classes), classical music and dance (Carnatic, "
             "Hindustani, Bharatanatyam, Kathak), and temple youth programs. Festivals, trips to "
             "India, cooking together, and kids' books in Indian languages all help. Look under the "
             "education and community categories, and ask Dost for classes in your area."},

    # --- food & cuisine (the diaspora's most-asked topic) ---
    {"slug": "biryani-guide", "title": "Biryani: styles & where to find it", "vertical": None,
     "text": "Biryani is a fragrant layered rice-and-meat (or vegetable) dish and one of the "
             "most-ordered Indian dishes in the US. Regional styles differ: Hyderabadi 'dum' biryani "
             "(spicy, slow-cooked, often with a boiled egg), Lucknowi/Awadhi (milder, aromatic), "
             "Kolkata (with potato and a subtle sweetness), Ambur and Dindigul (Tamil Nadu styles), "
             "and Sindhi. Vegetable, paneer, and egg biryanis are common vegetarian options, and "
             "most Indian restaurants and caterers across the US make it — many also cater it for "
             "parties. Ask about the spice level and whether it's cooked to order."},
    {"slug": "regional-indian-cuisines", "title": "Regional Indian cuisines, explained", "vertical": None,
     "text": "Indian food isn't one cuisine — it varies sharply by region. North Indian "
             "(Punjabi/Mughlai) features wheat breads (roti, naan), rich gravies, paneer, dal "
             "makhani, and tandoori dishes. South Indian (Tamil, Andhra, Karnataka, Kerala) centers "
             "on rice, dosa, idli, sambar, rasam, and coconut. West (Gujarati, Maharashtrian) leans "
             "vegetarian — thali, dhokla, pav bhaji; East (Bengali) is known for fish, mustard, and "
             "sweets. US Indian restaurants often specialize by region, so the 'best' place depends "
             "on what you're craving."},
    {"slug": "south-indian-food", "title": "South Indian food (dosa, idli & more)", "vertical": None,
     "text": "South Indian food, popular across the US, is largely rice- and lentil-based and heavily "
             "vegetarian. Staples include dosa (a crisp fermented crepe, plain or masala), idli "
             "(steamed cakes), vada, uttapam, and pongal — usually served with sambar (lentil-"
             "vegetable stew) and coconut chutney. Andhra and Telangana food is spicier (and the "
             "home of Hyderabadi biryani), while Kerala adds coconut and seafood. Filter coffee is "
             "the classic accompaniment, and many South Indian restaurants in the US are 'pure veg'."},
    {"slug": "north-indian-food", "title": "North Indian food (curries, naan, tandoor)", "vertical": None,
     "text": "North Indian cuisine — the style most Americans meet first — features wheat breads "
             "(roti, naan, paratha), creamy curries, and tandoor-grilled dishes. Favorites include "
             "butter chicken, chicken tikka masala, dal makhani, chana masala, palak/saag paneer, "
             "biryani, and tandoori kebabs. Punjabi and Mughlai influences make it rich and often "
             "mild-to-medium spiced — you can request the heat level. Vegetarians are well served "
             "with paneer and legume dishes."},
    {"slug": "street-food-chaat", "title": "Indian street food & chaat", "vertical": None,
     "text": "Chaat is India's beloved street food — tangy, crunchy, spicy snacks — and many US "
             "Indian restaurants and chaat houses serve it. Common items: pani puri / golgappa "
             "(crisp shells with spiced water), bhel puri, sev puri, dahi puri, aloo tikki chaat, "
             "pav bhaji, vada pav, and dabeli. It's mostly vegetarian and great for sharing; if "
             "you're new to it, start with pani puri or bhel."},
    {"slug": "thali-explained", "title": "What is a thali?", "vertical": None,
     "text": "A thali is a round platter holding several small bowls (katoris) so you can taste many "
             "dishes in one meal — typically dal, a vegetable or two, rice, roti, yogurt, pickle, "
             "papad, and a sweet. Regional thalis vary (Gujarati thalis are sweet-leaning and often "
             "all-you-can-eat; South Indian 'meals' are served on a banana leaf). It's a filling, "
             "good-value way to sample a region's home cooking — many US restaurants offer veg and "
             "non-veg thalis."},
    {"slug": "indian-catering", "title": "Indian catering for events", "vertical": "restaurants",
     "text": "For weddings, birthdays, pujas, Garba nights, and office parties, Indian catering is "
             "widely available across the US — many restaurants cater, plus dedicated Indian "
             "caterers and tiffin/meal services. When booking, confirm: cuisine/region and menu "
             "(veg/Jain/halal options), per-person price and minimums, delivery vs setup vs full "
             "service, lead time, and whether they provide chafing dishes and serving staff. Popular "
             "party dishes include biryani, chaat, tandoori platters, chole-bhature, dosa stations, "
             "and a sweets counter. Book early for festival and wedding season."},
    {"slug": "tiffin-services", "title": "Tiffin & home-style meal services", "vertical": "restaurants",
     "text": "A tiffin service delivers fresh, home-style Indian meals — usually dal, sabzi "
             "(vegetable), roti, and rice — on a daily or weekly plan. They're popular with students, "
             "bachelors, busy families, and new arrivals in US metros, offering an affordable "
             "alternative to cooking or eating out, often with veg, Jain, and regional (Gujarati, "
             "South Indian) options. Many also do party catering. Ask about delivery area, plan "
             "length, and customization."},
    {"slug": "indian-sweets-mithai", "title": "Indian sweets (mithai)", "vertical": None,
     "text": "Indian sweets (mithai) are central to festivals, weddings, and celebrations. Common "
             "ones: ladoo, barfi, gulab jamun, jalebi, rasgulla and rasmalai (Bengali), kaju katli "
             "(cashew), soan papdi, halwa, and peda. Sweet shops (halwai) and Indian grocers across "
             "the US stock them and make festival boxes for Diwali, Raksha Bandhan, and weddings. "
             "Most are vegetarian; eggless and sugar-free options are increasingly available."},
    {"slug": "chai-and-coffee", "title": "Chai & South Indian filter coffee", "vertical": None,
     "text": "Chai — black tea simmered with milk, sugar, and spices (cardamom, ginger, cinnamon) — "
             "is the everyday Indian drink, and 'masala chai' is on most US Indian menus and at chai "
             "cafes. In the south, strong filter coffee (decoction with milk) is the classic. 'Chai "
             "tea' is redundant (chai means tea); adrak (ginger) chai and cutting chai (a small "
             "strong serving) are popular variations."},
    {"slug": "indian-grocery-staples", "title": "Stocking an Indian kitchen in the US", "vertical": "groceries",
     "text": "Stocking an Indian kitchen in the US starts with atta (whole-wheat flour for roti), "
             "basmati rice, lentils (toor/moong/chana dal), and spices — turmeric, cumin, coriander, "
             "garam masala, red chili, mustard seeds. Add ghee, paneer, yogurt, onions/garlic/ginger, "
             "and frozen items (naan, parathas, samosas, peas). Indian grocers (Patel Brothers and "
             "many local desi stores) and online retailers carry everything, including regional "
             "brands and fresh produce like curry leaves, methi, and okra."},
    {"slug": "restaurant-types", "title": "Types of Indian restaurants in the US", "vertical": "restaurants",
     "text": "US Indian restaurants come in many styles: a 'dhaba' (rustic North Indian roadside "
             "style), 'udupi'/'pure veg' South Indian spots, fine-dining, all-you-can-eat lunch "
             "buffets, fast-casual and food trucks, chaat houses, sweet shops (halwai), and "
             "caterers/tiffin services. 'Pure veg' means no meat is cooked; halal meat is available "
             "at many. If you have dietary needs (Jain, vegan, gluten-free, nut allergy), call "
             "ahead — most kitchens can accommodate common Indian-diet requests."},

    # --- newcomer / "new in <city>" guides (one of the most common diaspora questions) ---
    {"slug": "newcomer-usa", "title": "New to the US: finding your Indian community", "vertical": None,
     "text": "Just moved to the US from India? Most metros have a strong Indian community clustered in "
             "particular suburbs, with Indian grocery stores, Hindu/Jain temples and gurdwaras, "
             "restaurants and sweet shops, classical music/dance and language classes for kids, and "
             "regional associations (Telugu, Tamil, Gujarati, Marathi, Bengali, Punjabi 'samaj' or "
             "'sangam'). Indian grocers are the easiest first stop — they post flyers for events, "
             "tutors, rentals, and priests. To get going, search this directory by your city or just "
             "ask Dost ('Indian groceries near me', 'Telugu association in my area', 'Hindu temple "
             "near me') in English, Hindi, or Telugu."},
    {"slug": "newcomer-dfw", "title": "New in Dallas–Fort Worth (DFW): the Indian community", "vertical": None,
     "text": "DFW has one of the fastest-growing Indian populations in the US, concentrated in the "
             "northern suburbs: Irving/Las Colinas/Coppell, Plano, Frisco, Carrollton, Richardson, "
             "McKinney, and Allen. You'll find many Indian grocery stores and restaurants, large Hindu "
             "temples (in Irving and Frisco), and active Telugu, Tamil, and Gujarati associations. "
             "Irving and Plano are popular first landing spots for renters. Use this directory for "
             "DFW restaurants, groceries, temples, doctors, and classes, or ask Dost for any city like "
             "Frisco or Plano."},
    {"slug": "newcomer-bay-area", "title": "New in the Bay Area: the Indian community", "vertical": None,
     "text": "The San Francisco Bay Area has a huge Indian-American (especially tech) community in the "
             "South Bay and East Bay: Fremont, Milpitas, San Jose, Sunnyvale, Santa Clara, and "
             "Cupertino, plus Dublin/Pleasanton and San Ramon. Fremont is a major hub with Indian "
             "grocers, restaurants, temples, and jewelry stores. Expect strong Telugu, Tamil, and "
             "Gujarati networks and many kids' Carnatic/Bharatanatyam classes. Search this directory "
             "by city (Fremont, San Jose, Sunnyvale) or ask Dost what's near you."},
    {"slug": "newcomer-nj-ny", "title": "New in New Jersey / New York: the Indian community", "vertical": None,
     "text": "The NY–NJ metro has one of the oldest, densest Indian communities. In New Jersey, "
             "Edison and Iselin (the famous Oak Tree Road corridor) are the heart — groceries, sari "
             "and jewelry shops, sweets, and restaurants — with more in Jersey City (India Square on "
             "Newark Avenue) and Parsippany. In New York, Jackson Heights (Queens) and Hicksville "
             "(Long Island) are key hubs. These areas have many temples and regional associations. "
             "Browse this directory by city or ask Dost."},
    {"slug": "newcomer-chicago", "title": "New in Chicago: the Indian community", "vertical": None,
     "text": "Chicagoland's Indian community is centered on Devon Avenue (Chicago's 'Little India') and "
             "the western suburbs — Naperville, Schaumburg, Aurora, Bartlett, and Hoffman Estates — "
             "which have Indian groceries, restaurants, temples, and active associations. Naperville "
             "and Schaumburg are popular family suburbs. Use this directory for groceries, temples, "
             "restaurants and classes by suburb, or ask Dost."},
    {"slug": "newcomer-atlanta", "title": "New in Atlanta: the Indian community", "vertical": None,
     "text": "Metro Atlanta's Indian community is concentrated north and northeast of the city — "
             "Alpharetta, Johns Creek, Suwanee, and Duluth (the Global Mall area on Satellite Blvd) — "
             "plus the large BAPS temple in Lilburn. You'll find Indian grocers, restaurants, sweet "
             "shops, and Telugu/Tamil/Gujarati associations. Browse this directory by suburb or ask "
             "Dost for temples, groceries, or doctors near you."},
    {"slug": "newcomer-houston", "title": "New in Houston: the Indian community", "vertical": None,
     "text": "Houston has a large Indian community, with the Hillcroft area (the 'Mahatma Gandhi "
             "District,' or Little India) full of groceries, sari/jewelry shops, and restaurants, and "
             "big family suburbs in Sugar Land, Katy, and Pearland. There are major temples (including "
             "BAPS and the Meenakshi temple in Pearland) and active regional associations. Search this "
             "directory by city or ask Dost."},
    {"slug": "newcomer-seattle", "title": "New in Seattle: the Indian community", "vertical": None,
     "text": "The Seattle area's Indian (largely tech) community is concentrated on the Eastside — "
             "Bellevue, Redmond, Sammamish, Bothell, and Issaquah — with Indian grocery stores, "
             "restaurants, temples, and kids' classical music/dance classes. Redmond and Sammamish are "
             "popular with families. Browse this directory by city or ask Dost what's nearby."},

    # --- practical newcomer Q&A ---
    {"slug": "find-language-doctor", "title": "Finding a Telugu/Hindi/Tamil-speaking doctor or professional",
     "vertical": "professionals",
     "text": "Many Indian-American doctors, dentists, CPAs, and lawyers speak Hindi, Telugu, Tamil, "
             "Gujarati, Punjabi, or other Indian languages, which helps when discussing health, taxes, "
             "or immigration in your own language. In this directory you can look for the language a "
             "provider speaks (where listed), or just ask Dost — for example, 'Telugu-speaking "
             "gynecologist in Irving' or 'Hindi-speaking CPA near me.' If a provider hasn't listed "
             "their languages yet, calling the office to ask is the surest way."},
    {"slug": "newcomer-banking-credit", "title": "Banking, SSN & credit for new arrivals", "vertical": None,
     "text": "New to the US, the practical first steps are usually: apply for an SSN (or an ITIN if "
             "you're not yet SSN-eligible), open a checking/savings account, and start building a US "
             "credit history — often with a secured credit card or a newcomer card, since you arrive "
             "with no US credit score. Pay bills on time and keep card balances low to build credit. "
             "Many Indian-American CPAs and financial advisors help newcomers; find one in this "
             "directory or ask Dost." + _DISCLAIMER},
    {"slug": "send-money-to-india", "title": "Sending money to India (remittances)", "vertical": "services",
     "text": "To send money from the US to India, people use bank wire transfers and specialized "
             "remittance services and apps (often with better exchange rates and lower fees than a "
             "bank, and fast bank-to-bank deposits). Compare the all-in cost: the exchange rate margin "
             "plus any transfer fee, and the delivery speed. Indian grocery stores and money-transfer "
             "service shops in most metros also offer remittance. You can find money-transfer services "
             "in this directory's services category or ask Dost." + _DISCLAIMER},
    {"slug": "oci-card", "title": "OCI card (Overseas Citizen of India) explained", "vertical": "services",
     "text": "An OCI (Overseas Citizen of India) card is a lifelong document for people of Indian "
             "origin, and their spouses, who have taken foreign citizenship — it lets you enter and "
             "live, work and study in India without a separate visa. Former Indian citizens usually "
             "must surrender their Indian passport and obtain a renunciation certificate before "
             "applying. In the US, OCI, visa, passport and attestation services are handled through "
             "VFS Global on behalf of the Indian embassy and consulates: you apply online, then submit "
             "documents to the center serving your state. Confirm current fees, documents and "
             "processing times on the official consulate / VFS website." + _DISCLAIMER},
    {"slug": "indian-passport-renewal", "title": "Renewing an Indian passport in the USA",
     "vertical": "services",
     "text": "Indian citizens in the US renew or reissue their passport through VFS Global, which "
             "processes applications for the Indian embassy and consulates. You apply online, submit "
             "documents, and the new passport is printed in India and mailed back — so plan well ahead, "
             "especially before travel. Common cases include normal renewal (expiry or pages full), "
             "name/address changes, and lost or damaged passports (which need a police report). Minors "
             "and first-time applicants have extra requirements. Always confirm the current process, "
             "fees and your jurisdiction on the official VFS / consulate site." + _DISCLAIMER},
    {"slug": "consulate-jurisdiction", "title": "Which Indian consulate serves your US state",
     "vertical": "services",
     "text": "Which Indian mission serves you depends on your US state. The Embassy of India is in "
             "Washington DC; Consulates General are in New York (Northeast), San Francisco (West), "
             "Chicago (Midwest), Houston (Texas and south-central), Atlanta (Southeast) and Seattle "
             "(Pacific Northwest). Passport, visa, OCI and attestation applications for your "
             "jurisdiction are processed through VFS Global. Jurisdictions occasionally change (for "
             "example when the Seattle consulate opened), so confirm which mission covers your state "
             "on the official website before applying. You can find the consulates in this directory."},
    {"slug": "find-h1b-sponsor", "title": "How to find an H-1B visa sponsor", "vertical": None,
     "text": "H-1B is the main work visa for skilled workers; most petitions need an employer to "
             "sponsor you and, for new H-1Bs, selection in the annual lottery. To find a sponsor: "
             "target employers that already file many H-1B petitions (large IT and consulting firms "
             "and many tech companies), check public U.S. Department of Labor disclosure data for who "
             "sponsors in your field and city, use your university career center if you are on F-1/OPT, "
             "and network within your profession. Changing employers (an 'H-1B transfer') generally "
             "does not require a new lottery. This directory's H-1B sponsors page lists top employers "
             "by certified applications, wages and locations." + _DISCLAIMER},
    {"slug": "find-a-pandit", "title": "Finding a pandit (priest) for a puja or ceremony",
     "vertical": "temples",
     "text": "For home ceremonies — griha pravesh (housewarming), weddings, satyanarayan puja, naming "
             "ceremonies, or last rites — families usually book a pandit (Hindu priest / purohit) "
             "through their local temple, which often keeps a list of priests for different traditions "
             "and languages, or by referral from the community. The temple or priest can advise on the "
             "muhurat (auspicious time), the samagri (materials) to arrange, and the specific rituals. "
             "Sikh and Jain ceremonies are arranged through the local gurdwara or Jain center. Find "
             "temples in this directory or ask Dost for one near you."},
    {"slug": "cricket-in-usa", "title": "Playing cricket in the USA", "vertical": None,
     "text": "Cricket is hugely popular in the Indian-American community, and the US scene is growing "
             "fast — from local metro leagues and clubs up to the national setup under USA Cricket and "
             "the professional Major League Cricket. Most big metros (Dallas, the Bay Area, New Jersey, "
             "Atlanta, Chicago, Houston, Seattle) have weekend leagues playing tape-ball and hard-ball "
             "cricket, with indoor cricket in winter and junior programs for kids. To get involved, "
             "look for a local league or club in your area — many welcome new players. Community "
             "associations and WhatsApp groups are the usual way people find a team."},
    {"slug": "renting-apartment-usa", "title": "Renting your first apartment in the USA", "vertical": None,
     "text": "Landlords typically check your credit and income, so newcomers with no US credit history "
             "may be asked for a larger deposit, a US-based co-signer/guarantor, or a few months' rent "
             "up front. Bring pay stubs or an offer letter, bank statements and ID. Read the lease for "
             "the term, deposit, and which utilities are included. Many Indian families start in areas "
             "with a strong desi community and good schools; Indian-American realtors can help you find "
             "a place. Find realtors in this directory or ask Dost about a specific metro." + _DISCLAIMER},
    {"slug": "bringing-parents-to-visit", "title": "Bringing your parents to visit the USA",
     "vertical": None,
     "text": "To bring parents from India to visit, they typically apply for a B-2 visitor (tourist) "
             "visa at a US consulate in India — there is no special 'parent visa'. They show ties to "
             "India and funds for the trip; you can support with an invitation letter and, if asked, an "
             "affidavit of support and your financial documents. Visitor stays are usually up to six "
             "months per entry. Because US healthcare is very expensive, most families buy visitor "
             "travel-medical insurance for the trip. Confirm current requirements on the US embassy / "
             "consulate in India and travel.state.gov." + _DISCLAIMER},
    {"slug": "shipping-to-india", "title": "Shipping parcels & cargo to India", "vertical": "services",
     "text": "To send parcels or cargo from the US to India, options range from international couriers "
             "(fast, pricier) to Indian-American cargo/shipping services that consolidate shipments "
             "(cheaper for boxes and bulk, slower by sea or air freight). For gifts and documents, a "
             "courier is simplest; for household goods or large boxes, a desi cargo service is usually "
             "cheaper. Compare per-kg cost, door-to-door vs pickup, insurance, and customs handling — "
             "the recipient in India may owe customs duty on higher-value items. Find shipping/cargo "
             "services in this directory's services category."},
    {"slug": "buying-a-car-usa", "title": "Buying your first car in the USA", "vertical": None,
     "text": "You can pay cash or finance, but auto loans need US credit history, so newcomers may face "
             "higher rates or need a larger down payment — some banks and credit unions offer newcomer "
             "auto loans. You'll need a driver's license (or learner's permit), auto insurance (required "
             "in almost every state), and to handle the title and registration at the DMV. Certified "
             "pre-owned cars add reliability and a warranty. Compare the full out-the-door price, not "
             "just the monthly payment, and get pre-approved financing so you can negotiate." + _DISCLAIMER},
]


def _all_articles() -> list[dict[str, Any]]:
    """Curated articles + the generated festival-timing article (refreshed yearly in festivals.py)."""
    from . import festivals
    return ARTICLES + [festivals.kb_article()]


def seed() -> dict[str, Any]:
    """Upsert the curated articles into the knowledge base (idempotent)."""
    from . import knowledge
    articles = _all_articles()
    added = unchanged = 0
    for a in articles:
        res = knowledge.upsert_document(
            source_type="article", source_ref=a["slug"], content=a["text"],
            vertical=a.get("vertical"), title=a["title"])
        if res.get("unchanged"):
            unchanged += 1
        elif res.get("ok"):
            added += 1
    return {"articles": len(articles), "indexed": added, "unchanged": unchanged}
