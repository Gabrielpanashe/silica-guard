"""Teach Mode's SMS-channel demonstration (22 August 2026).

The master reference document's Teach Mode (Section 1) is six illustrated
full-screen cards held up by the health worker during a 15-minute
pre-screening group session — that in-app UI is genuinely not built (see
docs/DEMO_GUIDE.md and SILICAGUARD.md for the honest status), and there was
no safe way to design/build/verify six new illustrated screens this close to
submission without design assets or a mobile build-and-verify loop in this
environment.

What's here instead is a pragmatic, real, working stand-in: the same six
topics as short EN+Shona SMS templates, broadcastable on demand to every
miner at a site via POST /api/education/broadcast (routers/education.py) —
reusing the exact bulk-send mechanism already built for the Outreach
Planner's 3-day/1-day announcement (services/notifications.py). This is a
genuine demonstration of "health education delivered to every miner at a
site," just over SMS instead of illustrated in-app cards — documented as
that substitution outright, not implied to be the full Teach Mode feature.

Draft copy — same not-yet-Clinical-Lead-signed-off caveat as every other
patient-facing string in this project (see backend/prompts/PENDING_CLINICAL_REVIEW.md).
"""

from typing import NamedTuple


class EducationTopic(NamedTuple):
    title: str
    message_en: str
    message_shona: str


TOPICS: dict[str, EducationTopic] = {
    "dust_danger": EducationTopic(
        title="What the dust does",
        message_en=(
            "SilicaGuard health tip: The fine dust from drilling and crushing rock "
            "settles deep in your lungs and stays there forever. You cannot cough it out."
        ),
        message_shona=(
            "SilicaGuard: Guruva rinobva pakuchera nekupwanya matombo rinonyura "
            "mumapapu enyu uye rinogara ikoko zvachose. Hamugone kufokorora kuti ribude."
        ),
    ),
    "silent_disease": EducationTopic(
        title="Why it's silent",
        message_en=(
            "SilicaGuard health tip: Silicosis can grow for years with no symptoms. "
            "Feeling fine today does not mean your lungs are fine. Get screened even if you feel healthy."
        ),
        message_shona=(
            "SilicaGuard: Silicosis inogona kukura kwemakore usina zviratidzo. "
            "Kunzwa zvakanaka nhasi hazvirevi kuti mapapu enyu akanaka. Enda unoongororwa kunyangwe uchinzwa uri mutano."
        ),
    ),
    "mask_that_works": EducationTopic(
        title="The mask that works",
        message_en=(
            "SilicaGuard health tip: A cloth mask does not stop silica dust. "
            "You need a proper respirator (N95 or better), fitted snugly, worn every time you drill or crush rock."
        ),
        message_shona=(
            "SilicaGuard: Musk yemucheka haidziviriri guruva reSilica. "
            "Munoda respirator chaiyo (N95 kana kupfuura), yakakodzera, muchipfeka nguva dzose pamunenge muchichera kana kupwanya."
        ),
    ),
    "water_suppression": EducationTopic(
        title="Water changes everything",
        message_en=(
            "SilicaGuard health tip: Wetting the rock face before and during drilling cuts the dust in the air "
            "by most of it. Ask your site to use wet drilling, every shift."
        ),
        message_shona=(
            "SilicaGuard: Kudiridza dombo musati mukachera uye pamunenge muchichera kunoderedza "
            "guruva mumhepo zvakanyanya. Kumbirai panzvimbo penyu pekushanda kuti pashandiswe wet drilling nguva dzose."
        ),
    ),
    "red_flag_signs": EducationTopic(
        title="The signs that mean go now",
        message_en=(
            "SilicaGuard health tip: Coughing blood, chest pain that won't go away, or breathlessness "
            "even at rest — these mean go to the hospital now, do not wait for the next outreach visit."
        ),
        message_shona=(
            "SilicaGuard: Kufokorora ropa, kurwadziwa nedumbu risingaperi, kana kupera "
            "mweya kunyangwe wakazorora — izvi zvinoreva kuti enda kuchipatara izvozvi, usamirira rwendo runotevera."
        ),
    ),
    "nssa_rights": EducationTopic(
        title="Your rights (NSSA compensation)",
        message_en=(
            "SilicaGuard health tip: If you are diagnosed with silicosis from mine work, you may be entitled "
            "to NSSA occupational disease compensation. Ask the clinic about the claims process."
        ),
        message_shona=(
            "SilicaGuard: Kana mukaonekwa nesilicosis inobva pabasa remugodhi, "
            "mungangodei makakodzera kuwana muripo weNSSA. Bvunzai kuchipatara nezve nzira yekutora muripo."
        ),
    ),
}
