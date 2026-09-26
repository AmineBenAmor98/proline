#!/usr/bin/env python3
"""Generate frontend/en/*.html from the French pages.

One explicit string map, so the two language trees cannot drift apart silently.
Run after editing any French page:

    python3 frontend/build_en.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
PAGES = ["index.html", "commercial.html", "soumission.html"]

# Links: French page -> English page. Applied before the text map.
LINKS = [
    ('href="/soumission?audience=residential"', 'href="/en/soumission?audience=residential"'),
    ('href="/soumission?audience=commercial"', 'href="/en/soumission?audience=commercial"'),
    ('href="/soumission"', 'href="/en/soumission"'),
    ('href="/commercial#apres-travaux"', 'href="/en/commercial#apres-travaux"'),
    ('href="/commercial"', 'href="/en/commercial"'),
    # The link and the id have to move together: rewriting only the href left
    # "Residential" on the English pages pointing at a section that is still
    # id="residentiel", so it scrolled nowhere.
    ('href="/#residentiel"', 'href="/en/#residential"'),
    ('id="residentiel"', 'id="residential"'),
    ('href="/#services"', 'href="/en/#services"'),
    ('href="/"', 'href="/en"'),
]

# The language switch must point back at French; marked first, restored last.
SWITCH = [
    ('href="/en/soumission">EN', "@@FR_SOUMISSION@@"),
    ('href="/en/commercial">EN', "@@FR_COMMERCIAL@@"),
    ('href="/en">EN', "@@FR_HOME@@"),
    # Footer switch: same idea, but the label is a word rather than "EN".
    ('href="/en/soumission">English', "@@FR_F_SOUMISSION@@"),
    ('href="/en/commercial">English', "@@FR_F_COMMERCIAL@@"),
    ('href="/en">English', "@@FR_F_HOME@@"),
]

TEXT = [
    ('lang="fr"', 'lang="en"'),
    ('data-locale="fr"', 'data-locale="en"'),
    # --- the English tree must declare ITSELF canonical, or Google drops it ---
    ('rel="canonical" href="https://proline-cleaningsolutions.com/"',
     'rel="canonical" href="https://proline-cleaningsolutions.com/en"'),
    ('rel="canonical" href="https://proline-cleaningsolutions.com/commercial"',
     'rel="canonical" href="https://proline-cleaningsolutions.com/en/commercial"'),
    ('rel="canonical" href="https://proline-cleaningsolutions.com/soumission"',
     'rel="canonical" href="https://proline-cleaningsolutions.com/en/soumission"'),
    ('property="og:url" content="https://proline-cleaningsolutions.com/"',
     'property="og:url" content="https://proline-cleaningsolutions.com/en"'),
    ('property="og:url" content="https://proline-cleaningsolutions.com/commercial"',
     'property="og:url" content="https://proline-cleaningsolutions.com/en/commercial"'),
    ('property="og:url" content="https://proline-cleaningsolutions.com/soumission"',
     'property="og:url" content="https://proline-cleaningsolutions.com/en/soumission"'),
    ('property="og:locale" content="fr_CA"', 'property="og:locale" content="en_CA"'),
    ("Proline Cleaning Solutions — Entretien ménager, Grand Montréal",
     "Proline Cleaning Solutions — Cleaning services, Greater Montreal"),
    ("Entretien ménager commercial à Montréal — Proline Cleaning Solutions",
     "Commercial cleaning in Montreal — Proline Cleaning Solutions"),
    ("Bureaux, commerces, immeubles et après-travaux. Soumission écrite sous 24 h.",
     "Offices, retail, buildings and post-construction. A written quote within 24 hours."),
    ("Prix en ligne pour les logements, soumission écrite sous 24 h pour les entreprises.",
     "An online price for homes, a written quote within 24 hours for businesses."),
    ('hreflang="en-ca" href="https://proline-cleaningsolutions.com/en', 'hreflang="en-ca" href="https://proline-cleaningsolutions.com/en'),
    # --- meta ---
    ("Entretien ménager commercial et résidentiel, Montréal", "Commercial and residential cleaning, Montreal"),
    ("Nettoyage commercial, industriel, résidentiel et post-construction à Montréal. Prix en ligne pour les logements, soumission écrite sous 24 h pour les entreprises.",
     "Commercial, industrial, residential and post-construction cleaning in Montreal. An online price for homes, a written quote within 24 hours for businesses."),
    ("Entretien de bureaux, commerces, immeubles et après-travaux à Montréal. Liste de tâches écrite par zone, soumission écrite sous 24 h.",
     "Cleaning for offices, retail, buildings and post-construction in Montreal. A written task list per zone, quote within 24 hours."),
    ("Obtenir un prix — Proline Cleaning Solutions", "Get a price — Proline Cleaning Solutions"),
    ("Obtenez votre prix de ménage résidentiel en ligne, ou votre soumission commerciale écrite sous 24 h. Montréal.",
     "Get your home cleaning price online, or your written commercial quote within 24 hours. Montreal."),
    ("Nettoyage commercial, industriel, résidentiel et post-construction.",
     "Commercial, industrial, residential and post-construction cleaning."),
    ("Bureaux, commerces, immeubles et après-travaux. Soumission écrite sous 24 h.",
     "Offices, retail, buildings and post-construction. A written quote within 24 hours."),
    ("Prix en ligne pour les logements, soumission écrite sous 24 h pour les entreprises.",
     "An online price for homes, a written quote within 24 hours for businesses."),
    # --- image alternatives -------------------------------------------------
    # Every other alt on the site was translated; these two -- the hero images --
    # were missed, so a screen reader on the English pages read French for the
    # largest image on each of them.
    ("Salon d'un condo montréalais fraîchement nettoyé, plancher de bois et comptoir de quartz",
     "Living room of a freshly cleaned Montreal condo, wood floor and quartz counter"),
    ("Corridor de bureaux au crépuscule, plancher poli et chariot d'entretien au fond",
     "Office hallway at dusk, polished floor and a cleaning cart at the far end"),
    # --- navigation ---
    (">Accueil<", ">Home<"),
    (">Commercial<", ">Commercial<"),
    (">Résidentiel<", ">Residential<"),
    (">Soumission<", ">Quote<"),
    # --- home ---
    ("Entretien ménager · Grand Montréal", "Cleaning services · Greater Montreal"),
    ("Des espaces propres, des affaires solides.", "Clean spaces, stronger businesses."),
    ("Nettoyage commercial, industriel, résidentiel et post-construction à Montréal. Prix en ligne en deux minutes pour les logements, soumission écrite sous 24 h pour les entreprises.",
     "Commercial, industrial, residential and post-construction cleaning in Montreal. An online price in two minutes for homes, a written quote within 24 hours for businesses."),
    ("Votre prix affiché à l'écran, immédiatement.", "Your price on screen, right away."),
    ("Calculer mon prix", "Calculate my price"),
    ("Bureaux, commerces, immeubles, après-travaux.", "Offices, retail, buildings, post-construction."),
    ("Demander une soumission", "Request a quote"),
    ("Assurée et cautionnée", "Insured and bonded"),
    ("Produits et équipement fournis", "Products and equipment supplied"),
    ("Satisfaction garantie ou reprise", "Satisfaction guaranteed or we come back"),
    ("[NOMBRE] avis Google", "[NUMBER] Google reviews"),
    ("Un seul fournisseur, du condo à l'immeuble de bureaux.", "One provider, from a condo to an office building."),
    ("Ménage résidentiel", "Home cleaning"),
    ("Récurrent ou ponctuel, avec liste de tâches convenue par pièce.", "Recurring or one-time, with an agreed task list per room."),
    ("Prix en ligne", "Online price"),
    ("Bureaux et commerces", "Offices and retail"),
    ("Passages du soir ou de nuit, selon vos heures d'accès.", "Evening or night visits, around your access hours."),
    ("Soumission 24 h", "Quote in 24h"),
    ("Immeubles et copropriétés", "Buildings and condos"),
    ("Aires communes, corridors, escaliers et entrées.", "Common areas, hallways, stairwells and entrances."),
    ("Fin de bail", "End of lease"),
    ("Remise en état d'un logement entre deux locataires.", "Turnover cleaning between two tenants."),
    ("Post-construction", "Post-construction"),
    ("Poussière fine, résidus, vitres et finition avant livraison.", "Fine dust, residue, windows and finishing before handover."),
    ("Décapage et cirage", "Floor stripping and waxing"),
    ("Décapage, scellant et cirage pour vinyle, terrazzo et béton.", "Stripping, sealing and waxing for vinyl, terrazzo and concrete."),
    ("Spécialité Proline", "Proline specialty"),
    ("Votre prix en deux minutes, sans appel.", "Your price in two minutes, no phone call."),
    ("Chambres, salles de bain, superficie, fréquence. Le prix s'affiche, vous réservez votre date. Aucune visite préalable pour un logement standard.",
     "Bedrooms, bathrooms, area, frequency. The price appears, you book your date. No site visit for a standard home."),
    ("Rabais sur le service récurrent", "A discount on recurring service"),
    ("Même équipe à chaque visite", "The same team every visit"),
    ("Annulation gratuite jusqu'à 24 h avant", "Free cancellation up to 24 hours before"),
    ("Aperçu du calculateur", "Calculator preview"),
    ("3 chambres", "3 bedrooms"),
    ("2 salles de bain", "2 bathrooms"),
    # --- structured data and the quote page's social card ---
    ("Obtenir un prix — Proline Cleaning Solutions", "Get a price — Proline Cleaning Solutions"),
    ("Votre prix en ligne en deux minutes pour un logement, soumission écrite sous 24 h pour un local commercial.",
     "Your price online in two minutes for a home, a written quote within 24 hours for a commercial space."),
    ('"name":"Entretien ménager commercial"', '"name":"Commercial cleaning"'),
    ('"name":"Entretien ménager résidentiel"', '"name":"Residential cleaning"'),
    ('"name":"Nettoyage post-construction"', '"name":"Post-construction cleaning"'),
    ('"name":"Décapage et cirage de planchers"', '"name":"Floor stripping and waxing"'),
    ('"serviceType":"Entretien ménager commercial et industriel"',
     '"serviceType":"Commercial and industrial cleaning"'),
    ('"url":"https://proline-cleaningsolutions.com/commercial"', '"url":"https://proline-cleaningsolutions.com/en/commercial"'),
    ('"url":"https://proline-cleaningsolutions.com/"', '"url":"https://proline-cleaningsolutions.com/en"'),
    ("Bureaux, commerces, immeubles, industriel et post-construction. Soumission écrite sous 24 h.",
     "Offices, retail, buildings, industrial and post-construction. A written quote within 24 hours."),
    ("Nettoyage commercial, industriel, résidentiel et post-construction.",
     "Commercial, industrial, residential and post-construction cleaning."),
    ("[SUP] pi²", "[AREA] sq ft"),
    ("[PRIX] $", "[PRICE] $"),
    ("par visite · aux deux semaines", "per visit · every two weeks"),
    ("Estimation ferme pour un logement standard. Un cas particulier est confirmé avant la première visite.",
     "A firm price for a standard home. Anything unusual is confirmed before the first visit."),
    ("Comment ça marche", "How it works"),
    ("Trois étapes, aucune zone grise.", "Three steps, no grey areas."),
    ("Vous décrivez les lieux", "You describe the space"),
    ("Type de local, superficie, fréquence. Les photos sont facultatives.", "Type of space, area, frequency. Photos are optional."),
    ("Vous recevez votre prix", "You get your price"),
    ("Immédiatement pour un logement, sous 24 h pour un local commercial.", "Instantly for a home, within 24 hours for a commercial space."),
    ("On s'occupe du reste", "We handle the rest"),
    ("Horaire fixe, même équipe, suivi après les premières visites.", "A fixed schedule, the same team, follow-up after the first visits."),
    ("Prêt à déléguer l'entretien ?", "Ready to hand over the cleaning?"),
    ("Obtenez votre prix résidentiel à l'écran, ou votre soumission commerciale sous 24 h.",
     "Get your home price on screen, or your commercial quote within 24 hours."),
    ("Obtenir un prix", "Get a price"),
    # --- floor care section ---
    ("Des planchers qui ont l'air neufs, pas seulement propres.", "Floors that look new, not just clean."),
    ("Décapage complet, scellant et cirage pour vinyle, terrazzo et béton. Le fini revient, et il tient : corridors, entrées, salles communes et planchers de vente.",
     "Full stripping, sealer and wax for vinyl, terrazzo and concrete. The finish comes back, and it lasts: hallways, entrances, common rooms and sales floors."),
    ("Décapage des couches de cire usées", "Stripping of worn wax layers"),
    ("Scellant et deux à quatre couches de fini", "Sealer and two to four coats of finish"),
    ("Polissage haute vitesse, résultat uniforme", "High-speed burnishing, an even result"),
    ("Planifié hors des heures d'ouverture", "Scheduled outside your opening hours"),
    ("Polisseuse en action sur un plancher de terrazzo fraîchement ciré",
     "A floor burnisher at work on freshly waxed terrazzo"),
    ("Spécialité Proline →", "Proline specialty →"),
    ("Voir la méthode →", "See how we do it →"),
    # --- home: décapage before / after ---
    ("Corridor de tuiles de vinyle avant décapage : rayures, marques de talon et fini terne",
     "A vinyl tile corridor before stripping: scratches, heel marks and a dull finish"),
    ("Le même corridor après décapage et cirage : les luminaires se reflètent dans le plancher",
     "The same corridor after stripping and waxing: the light fixtures reflect in the floor"),
    (">Avant<", ">Before<"),
    (">Après<", ">After<"),
    ("Fini usé, rayures et marques de talon.", "Worn finish, scratches and heel marks."),
    ("Le même corridor, décapé, scellé et ciré.", "The same corridor, stripped, sealed and waxed."),
    # --- home: l'équipe ---
    ("L'équipe", "The crew"),
    ("Les mêmes visages, semaine après semaine.", "The same faces, week after week."),
    ("Une équipe attitrée à votre adresse, qui connaît vos lieux, vos consignes et vos heures. Pas quelqu'un de nouveau à former chaque mois.",
     "A crew assigned to your address, who know the place, your instructions and your hours. Not someone new to train every month."),
    ("Personnel en uniforme, identifiable dès l'arrivée", "Uniformed staff, identifiable on arrival"),
    ("Vos consignes d'accès et vos priorités notées au dossier", "Your access instructions and priorities kept on file"),
    ("Remplacement planifié en cas d'absence", "Planned cover when someone is away"),
    ("Un responsable joignable directement, pas un centre d'appels", "A supervisor you reach directly, not a call centre"),
    ("Parler à un responsable", "Talk to a supervisor"),
    ("Deux employés Proline en uniforme marine traversant un hall de bureaux avec leur chariot et leurs produits",
     "Two Proline staff in navy uniforms crossing an office lobby with their cart and supplies"),
    # --- commercial ---
    ("Commercial · Grand Montréal", "Commercial · Greater Montreal"),
    ("Un immeuble propre, un seul interlocuteur.", "A clean building, one point of contact."),
    ("Bureaux, commerces, aires communes, industriel léger et après-travaux. Programme adapté à vos heures d'accès, soumission écrite sous 24 h.",
     "Offices, retail, common areas, light industrial and post-construction. A program built around your access hours, written quote within 24 hours."),
    ("Obtenir une soumission", "Request a quote"),
    ("Planifier un appel", "Schedule a call"),
    ("Ce qui est inclus", "What is included"),
    ("Bureau aux murs crème et panneaux marine, postes de travail et aire de détente sous de hautes fenêtres",
     "An office with cream walls and navy panels, workstations and a lounge area under tall windows"),
    ("Une liste de tâches écrite, zone par zone.", "A written task list, zone by zone."),
    ("Vous savez ce qui est fait à chaque passage et ce qui revient une fois par saison. Aucune surprise à la facturation.",
     "You know what happens at every visit and what comes back once a season. No surprises on the invoice."),
    ("Planchers", "Floors"),
    ("Balayage, lavage et entretien selon le revêtement.", "Sweeping, washing and care by surface type."),
    ("Sanitaires", "Restrooms"),
    ("Désinfection complète et réapprovisionnement.", "Full disinfection and restocking."),
    ("Surfaces de contact", "Touch points"),
    ("Poignées, interrupteurs, rampes et boutons d'ascenseur.", "Handles, switches, railings and elevator buttons."),
    ("Ordures et recyclage", "Waste and recycling"),
    ("Collecte, sortie des bacs et rotation.", "Collection, bin rotation and curbside."),
    ("Cuisinettes et vitres", "Kitchenettes and glass"),
    ("Salles de repos, comptoirs et vitres intérieures.", "Break rooms, counters and interior windows."),
    ("Travaux périodiques", "Periodic work"),
    ("Tapis, décapage et cirage, garages.", "Carpets, stripping and waxing, garages."),
    # --- commercial: sanitaires ---
    ("Salle de toilette commerciale entretenue : comptoir, miroirs et plancher de béton poli",
     "A maintained commercial restroom: vanity, mirrors and polished concrete floor"),
    ("C'est la pièce sur laquelle on vous juge.", "This is the room you get judged on."),
    ("Personne ne remarquera le corridor lavé hier soir. La salle de toilette, oui. Nous la traitons en conséquence, à chaque passage.",
     "Nobody notices the corridor we washed last night. The restroom, they notice. We treat it accordingly, on every visit."),
    ("Désinfection des cuvettes, urinoirs, lavabos et robinetterie", "Toilets, urinals, sinks and fixtures disinfected"),
    ("Miroirs, distributrices et surfaces de contact", "Mirrors, dispensers and high-touch surfaces"),
    ("Réapprovisionnement du papier, du savon et des sacs", "Paper, soap and liners restocked"),
    ("Registre de passage signé, affiché sur demande", "A signed service log, posted on request"),
    # --- commercial: après-travaux ---
    ("Après-travaux", "Post-construction"),
    ("Un local prêt à ouvrir, pas seulement balayé.", "A space ready to open, not just swept."),
    ("La poussière de construction se redépose deux ou trois fois avant de disparaître. Nous revenons jusqu'à ce que les surfaces restent propres, et nous nous alignons sur votre date de livraison.",
     "Construction dust settles two or three times before it is gone. We come back until the surfaces stay clean, and we work to your handover date."),
    ("Poussière fine retirée des surfaces hautes comme basses", "Fine dust removed from high and low surfaces alike"),
    ("Résidus de peinture, d'adhésif et d'autocollants", "Paint, adhesive and sticker residue"),
    ("Vitres, cadrages, luminaires et quincaillerie", "Glass, frames, light fixtures and hardware"),
    ("Dernier passage juste avant la remise des clés", "A final visit right before the keys change hands"),
    ("Planifier la prise de possession", "Schedule the handover clean"),
    ("Nettoyage après travaux : poussière fine essuyée sur le rebord d'une fenêtre, échelle et toile de protection au fond",
     "Post-construction cleaning: fine dust wiped from a window sill, ladder and protective sheeting behind"),
    ("Notre façon de chiffrer", "How we price"),
    ("La superficie seule ne dit pas le prix.", "Square footage alone does not set the price."),
    ("Deux locaux de même taille ne demandent pas le même temps. Trois facteurs déterminent votre soumission.",
     "Two spaces of the same size need different amounts of work. Three factors set your quote."),
    ("Les zones et leurs surfaces", "The zones and their surfaces"),
    ("Nombre de sanitaires, type de plancher, mobilier à contourner, escaliers.", "Number of restrooms, floor type, furniture to work around, stairs."),
    ("La fréquence et les accès", "Frequency and access"),
    ("Passages par semaine, heures d'ouverture, stationnement, clés et alarme.", "Visits per week, opening hours, parking, keys and alarm."),
    ("Les travaux périodiques", "Periodic work"),
    ("Chiffrés séparément de l'entretien courant, pour comparer à portée égale.", "Quoted separately from routine cleaning, so proposals compare fairly."),
    ("Votre soumission écrite sous 24 h.", "Your written quote within 24 hours."),
    ("Décrivez votre immeuble en trois minutes. Notre équipe révise chaque prix avant l'envoi.",
     "Describe your building in three minutes. Our team reviews every price before it goes out."),
    ("Commencer ma demande", "Start my request"),
    ("Étapes du formulaire", "Form steps"),
    # --- quote wizard: property tiles ---
    ("Quel type de lieu ?", "What kind of place is it?"),
    (">Maison<", ">House<"),
    (">Condo<", ">Condo<"),
    (">Appartement<", ">Apartment<"),
    (">Bureau<", ">Office<"),
    (">Commerce<", ">Retail<"),
    (">Immeuble<", ">Building<"),
    (">Industriel<", ">Industrial<"),
    (">Chantier<", ">Construction site<"),
    ("Votre estimation", "Your estimate"),
    ("Choisissez un type de lieu", "Pick a type of place"),
    # --- service labels that were still French on the English page ---
    ("> Bureaux</label>", "> Offices</label>"),
    ("> Fin de bail</label>", "> End of lease</label>"),
    ("> Tapis</label>", "> Carpets</label>"),
    # --- quote wizard ---
    ("Demande de soumission", "Quote request"),
    ("Votre prix, en trois étapes.", "Your price, in three steps."),
    ("Répondez à quelques questions. Pour un logement, le prix s'affiche tout de suite ; pour un local commercial, notre équipe le révise et vous l'envoie sous 24 h.",
     "Answer a few questions. For a home the price appears right away; for a commercial space our team reviews it and sends it within 24 hours."),
    ("01 · La propriété", "01 · The property"),
    ("02 · Le besoin", "02 · The need"),
    ("03 · Vos coordonnées", "03 · Your details"),
    ("Superficie approximative (pi²)", "Approximate area (sq ft)"),
    (">Maison<", ">House<"), (">Condo<", ">Condo<"), (">Appartement<", ">Apartment<"),
    (">Bureau<", ">Office<"), (">Commerce<", ">Retail<"), (">Immeuble<", ">Building<"),
    (">Industriel<", ">Industrial<"),
    ("Chambres", "Bedrooms"),
    ("Salles de bain", "Bathrooms"),
    ("Nombre de sanitaires", "Number of restrooms"),
    ("Nombre d'étages", "Number of floors"),
    ("Passages de soir ou de nuit", "Evening or night visits"),
    ("Continuer", "Continue"),
    ("Retour", "Back"),
    ("Fréquence", "Frequency"),
    ("Une seule fois", "One time"),
    ("Aux 2 semaines", "Every 2 weeks"),
    ("Chaque semaine", "Weekly"),
    ("Mensuel", "Monthly"),
    ("Services recherchés", "Services needed"),
    ("Aires communes", "Common areas"),
    # The extras themselves are no longer in the page: the form renders them from
    # the rate card, which carries both languages. Only the group label is markup.
    ("Extras", "Extras"),
    ("Début souhaité", "Preferred start"),
    ("Accès et contraintes", "Access and constraints"),
    ("Horaires, stationnement, zones prioritaires…", "Hours, parking, priority areas…"),
    ("Nom complet *", "Full name *"),
    ("Entreprise ou syndicat", "Company or condo board"),
    ("Courriel", "Email"),
    ("Téléphone", "Phone"),
    ("Un courriel ou un téléphone suffit. Nous utilisons le canal que vous préférez.",
     "An email or a phone number is enough. We use whichever you prefer."),
    ("J'accepte que ces renseignements servent à répondre à ma demande.",
     "I agree that this information may be used to answer my request."),
    # --- the optional photo block; the picker's own labels live in photos.js ---
    ("Le prix dépend surtout de l'état des lieux. Avec quelques photos, nous confirmons un prix exact ; sans photos, l'estimation reste à valider sur place.",
     "The price depends mostly on the state of the place. With a few photos we can confirm an exact price; without them, the estimate still has to be checked on site."),
    ("Vos photos servent uniquement à préparer votre soumission. Elles sont conservées un an, puis supprimées.",
     "Your photos are used only to prepare your quote. They are kept for one year and then deleted."),
    ("Envoi des photos", "Uploading photos"),
    ("Vous pouvez fermer cette page — votre demande est déjà enregistrée.",
     "You can close this page — your request is already saved."),
    ("Facultatif", "Optional"),
    ("Ne pas remplir", "Do not fill"),
    ("Envoyer ma demande", "Send my request"),
    ("Votre estimation", "Your estimate"),
    ("Remplissez la propriété et la fréquence : le prix apparaît ici.",
     "Fill in the property and frequency: your price appears here."),
    ("Taxes en sus. Estimation ferme pour un logement standard.", "Taxes extra. A firm price for a standard home."),
    ("Une question ?", "A question?"),
    ("Retour à l'accueil", "Back to home"),
    # --- footer ---
    ("Nettoyage commercial, industriel, résidentiel et post-construction, incluant le décapage et le cirage. Grand Montréal.",
     "Commercial, industrial, residential and post-construction cleaning, including floor stripping and waxing. Greater Montreal."),
    ("Suivez-nous sur Facebook", "Follow us on Facebook"),
    (">Services<", ">Services<"),
    (">Secteurs<", ">Areas<"),
    (">Nous joindre<", ">Contact<"),
    ("Lun–ven, 8 h–18 h", "Mon–Fri, 8am–6pm"),
    ("[Confidentialité] · [Conditions]", "[Privacy] · [Terms]"),
    ("Appeler", "Call"),
]


# Applied longest source first. In file order, a short entry destroyed the tail
# of a longer one that had not run yet: ("Retour", "Back") shipped
# "Back à l'accueil" on the English success page, and three other strings went
# out half-translated the same way. Length ordering makes that impossible.
ORDERED = sorted(TEXT, key=lambda pair: len(pair[0]), reverse=True)
USED: set[str] = set()


def translate(html: str) -> str:
    for needle, marker in SWITCH:
        html = html.replace(needle, marker)
    for src, dst in LINKS:
        html = html.replace(src, dst)
    html = html.replace("@@FR_SOUMISSION@@", 'href="/soumission">FR')
    html = html.replace("@@FR_COMMERCIAL@@", 'href="/commercial">FR')
    html = html.replace("@@FR_HOME@@", 'href="/">FR')
    html = html.replace("@@FR_F_SOUMISSION@@", 'href="/soumission">Français')
    html = html.replace("@@FR_F_COMMERCIAL@@", 'href="/commercial">Français')
    html = html.replace("@@FR_F_HOME@@", 'href="/">Français')
    for src, dst in ORDERED:
        if src in html:
            USED.add(src)
        html = html.replace(src, dst)
    return html


# Words that are French but belong on the English pages anyway.
ALLOWED = {"Français", "Montréal", "Proline"}

# Text the checker should not read: the language switch, and the JSON-LD address
# where "Montréal" is the city's name rather than a word to translate.
VISIBLE = re.compile(r"<(script|style)[\s\S]*?</\1>")
TEXT_AND_ATTRS = re.compile(
    r'>([^<]+)<|(?:alt|title|content|placeholder|aria-label)="([^"]*)"'
)
ACCENTED = re.compile(r"\b\w*[àâäçéèêëîïôöùûüœ]\w*\b", re.IGNORECASE)


def leftovers(html: str) -> list[str]:
    """French that reached an English page.

    The old check was a five-word hand-written list, which is why a half-French
    meta description, a French alt on the hero image and a "Back à l'accueil"
    button all shipped without a warning. Anything accented in visible text or in
    an attribute a human or a screen reader reads is suspect, and the allowlist
    is short enough to stay honest.
    """
    body = VISIBLE.sub("", html)
    found = []
    for text, attr in TEXT_AND_ATTRS.findall(body):
        for word in ACCENTED.findall(text or attr):
            if word not in ALLOWED and word not in found:
                found.append(word)
    return found


def main() -> int:
    out_dir = ROOT / "en"
    out_dir.mkdir(exist_ok=True)
    problems = 0
    for name in PAGES:
        source = (ROOT / name).read_text(encoding="utf-8")
        english = translate(source)
        (out_dir / name).write_text(english, encoding="utf-8")
        print(f"wrote en/{name}")
        found = leftovers(english)
        if found:
            problems += 1
            print(f"  FRENCH LEFT IN en/{name}: {', '.join(found)}")

    # An entry that matches nothing is the map drifting away from the pages it
    # describes -- the exact failure this file exists to prevent, so it is
    # reported rather than left to rot.
    dead = [src for src, _ in TEXT if src not in USED]
    if dead:
        print(f"  {len(dead)} map entries matched nothing:")
        for src in dead:
            print(f"    {src!r}")
        problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
