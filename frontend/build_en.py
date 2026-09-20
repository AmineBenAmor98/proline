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
    ('href="/#residentiel"', 'href="/en/#residential"'),
    ('href="/#services"', 'href="/en/#services"'),
    ('href="/"', 'href="/en"'),
]

# The language switch must point back at French; marked first, restored last.
SWITCH = [
    ('href="/en/soumission">EN', "@@FR_SOUMISSION@@"),
    ('href="/en/commercial">EN', "@@FR_COMMERCIAL@@"),
    ('href="/en">EN', "@@FR_HOME@@"),
]

TEXT = [
    ('lang="fr"', 'lang="en"'),
    ('data-locale="fr"', 'data-locale="en"'),
    ('hreflang="en-ca" href="https://prolinesolutions.ca/en', 'hreflang="en-ca" href="https://prolinesolutions.ca/en'),
    # --- meta ---
    ("Entretien ménager commercial et résidentiel, Montréal", "Commercial and residential cleaning, Montreal"),
    ("Nettoyage commercial, industriel, résidentiel et post-construction à Montréal. Prix en ligne pour les logements, soumission écrite sous 24 h pour les entreprises.",
     "Commercial, industrial, residential and post-construction cleaning in Montreal. An online price for homes, a written quote within 24 hours for businesses."),
    ("Entretien ménager commercial à Montréal", "Commercial cleaning in Montreal"),
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
    ('og:locale" content="fr_CA"', 'og:locale" content="en_CA"'),
    ('og:url" content="https://prolinesolutions.ca/commercial"', 'og:url" content="https://prolinesolutions.ca/en/commercial"'),
    ('og:url" content="https://prolinesolutions.ca/"', 'og:url" content="https://prolinesolutions.ca/en"'),
    # --- navigation ---
    (">Accueil<", ">Home<"),
    ("> Résidentiel</label>", "> Residential</label>"),
    ("> Commercial</label>", "> Commercial</label>"),
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
    ("[PHOTO — équipe Proline au travail]", "[PHOTO — the Proline team at work]"),
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
    ("[SUP] pi²", "[AREA] sq ft"),
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
    ("[PHOTO — corridor ou bureau entretenu]", "[PHOTO — a maintained hallway or office]"),
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
    ("> Tapis</label>", "> Carpets</label>"),
    # --- quote wizard ---
    ("Demande de soumission", "Quote request"),
    ("Votre prix, en trois étapes.", "Your price, in three steps."),
    ("Répondez à quelques questions. Pour un logement, le prix s'affiche tout de suite ; pour un local commercial, notre équipe le révise et vous l'envoie sous 24 h.",
     "Answer a few questions. For a home the price appears right away; for a commercial space our team reviews it and sends it within 24 hours."),
    ("01 · La propriété", "01 · The property"),
    ("02 · Le besoin", "02 · The need"),
    ("03 · Vos coordonnées", "03 · Your details"),
    ("Type de demande", "Type of request"),
    ("Type de propriété", "Property type"),
    ("Superficie approximative (pi²)", "Approximate area (sq ft)"),
    (">Maison<", ">House<"), (">Condo<", ">Condo<"), (">Appartement<", ">Apartment<"),
    (">Bureau<", ">Office<"), (">Commerce<", ">Retail<"), (">Immeuble<", ">Building<"),
    (">Industriel<", ">Industrial<"), (">Chantier / après-travaux<", ">Construction site<"),
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
    (">Tapis<", ">Carpets<"),
    (">Bureaux<", ">Offices<"),
    ("Extras", "Extras"),
    ("Intérieur du réfrigérateur", "Inside the fridge"),
    ("Intérieur du four", "Inside the oven"),
    ("Vitres intérieures", "Interior windows"),
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
    ("Ne pas remplir", "Do not fill"),
    ("Envoyer ma demande", "Send my request"),
    ("Votre estimation", "Your estimate"),
    ("Remplissez la propriété et la fréquence : le prix apparaît ici.",
     "Fill in the property and frequency: your price appears here."),
    ("Taxes en sus. Estimation ferme pour un logement standard.", "Taxes extra. A firm price for a standard home."),
    ("Une question ?", "A question?"),
    ("Retour à l'accueil", "Back to home"),
    ("Remplir le formulaire", "Open the form"),
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
    ("English", "Français"),
]


def translate(html: str) -> str:
    for needle, marker in SWITCH:
        html = html.replace(needle, marker)
    for src, dst in LINKS:
        html = html.replace(src, dst)
    html = html.replace("@@FR_SOUMISSION@@", 'href="/soumission">FR')
    html = html.replace("@@FR_COMMERCIAL@@", 'href="/commercial">FR')
    html = html.replace("@@FR_HOME@@", 'href="/">FR')
    for src, dst in TEXT:
        html = html.replace(src, dst)
    return html


def main() -> int:
    out_dir = ROOT / "en"
    out_dir.mkdir(exist_ok=True)
    for name in PAGES:
        source = (ROOT / name).read_text(encoding="utf-8")
        (out_dir / name).write_text(translate(source), encoding="utf-8")
        print(f"wrote en/{name}")

    # Anything still obviously French in the English tree is a missing entry.
    suspects = ["Soumission", "Résidentiel", "Superficie", "Courriel", "Envoyer"]
    for name in PAGES:
        text = (out_dir / name).read_text(encoding="utf-8")
        body = re.sub(r"<(script|style)[\s\S]*?</\1>", "", text)
        found = [word for word in suspects if word in body]
        if found:
            print(f"  warning: en/{name} still contains {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
