#!/usr/bin/env python3
"""Generate the four legal pages from one shell, so FR and EN cannot drift.

    python3 frontend/build_legal.py

WHY A GENERATOR. The footer of every page linked to `[Confidentialité]` and
`[Conditions]` -- placeholders in square brackets, pointing nowhere. Quebec's Law
25 requires a privacy policy from any business collecting personal information,
and this one collects names, telephone numbers, home addresses and PHOTOGRAPHS OF
THE INSIDE OF PEOPLE'S HOMES. The quote form also promises those photos are
deleted after a year; before this, that promise was written nowhere a customer
could read it.

Everything stated in these pages is taken from what the code actually does:
retention from `photo_retention_days`, the hosting region from
`Pulumi.prod.yaml`, the browser storage from `quote.js`, and the service promises
from the claims already made on the home page. Nothing here is aspirational.

Re-run after editing the CONTENT dictionaries below; the pages are generated
files and editing them directly will be overwritten.
"""

import pathlib

HERE = pathlib.Path(__file__).resolve().parent

NAV = {
    "fr": """    <nav class="site-nav">
      <a class="navlink" href="/">Accueil</a>
      <a class="navlink" href="/commercial">Commercial</a>
      <a class="navlink" href="/#residentiel">Résidentiel</a>
      <a class="lang" href="{alt}">EN</a>
      <a class="phone" href="tel:+15142424779">514&nbsp;242-4779</a>
      <a class="btn btn-primary" href="/soumission">Obtenir un prix</a>
    </nav>""",
    "en": """    <nav class="site-nav">
      <a class="navlink" href="/en">Home</a>
      <a class="navlink" href="/en/commercial">Commercial</a>
      <a class="navlink" href="/en/#residential">Residential</a>
      <a class="lang" href="{alt}">FR</a>
      <a class="phone" href="tel:+15142424779">514&nbsp;242-4779</a>
      <a class="btn btn-primary" href="/en/soumission">Get a price</a>
    </nav>""",
}

FOOTER = {
    "fr": """<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-col">
        <a class="brand" href="/" style="margin-bottom:6px">
          <img src="/img/logo.png" alt="" width="38" height="38">
          <span class="brand-text">
            <span class="brand-name">PROLINE</span>
            <span class="brand-sub">Cleaning Solutions</span>
          </span>
        </a>
        <p>Nettoyage commercial, industriel, résidentiel et post-construction, incluant le décapage et le cirage. Grand Montréal.</p>
        <a href="https://www.facebook.com/people/Proline-Solutions/61581957144456/" rel="noopener">Suivez-nous sur Facebook</a>
      </div>
      <div class="footer-col">
        <h4>Services</h4>
        <a href="/#residentiel">Résidentiel</a>
        <a href="/commercial">Commercial</a>
        <a href="/commercial#apres-travaux">Post-construction</a>
        <a href="/#decapage">Décapage et cirage</a>
      </div>
      <div class="footer-col">
        <h4>Secteurs desservis</h4>
        <p>Montréal, Laval, Longueuil, la Rive-Nord et la Rive-Sud.</p>
      </div>
      <div class="footer-col">
        <h4>Nous joindre</h4>
        <a href="tel:+15142424779">514 242-4779</a>
        <a href="mailto:contact@proline-cleaningsolutions.com">contact@proline-cleaningsolutions.com</a>
        <span class="note">Lun–ven, 8 h–18 h</span>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Proline Cleaning Solutions</span>
      <span><a href="/">Accueil</a> · <a href="/soumission">Soumission</a> · <a href="{alt}">English</a></span>
      <span><a href="/confidentialite">Confidentialité</a> · <a href="/conditions">Conditions</a></span>
    </div>
  </div>
</footer>

<div class="callbar">
  <a class="btn btn-ghost" href="tel:+15142424779">Appeler</a>
  <a class="btn btn-primary" href="/soumission">Obtenir un prix</a>
</div>""",
    "en": """<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div class="footer-col">
        <a class="brand" href="/en" style="margin-bottom:6px">
          <img src="/img/logo.png" alt="" width="38" height="38">
          <span class="brand-text">
            <span class="brand-name">PROLINE</span>
            <span class="brand-sub">Cleaning Solutions</span>
          </span>
        </a>
        <p>Commercial, industrial, residential and post-construction cleaning, including floor stripping and waxing. Greater Montreal.</p>
        <a href="https://www.facebook.com/people/Proline-Solutions/61581957144456/" rel="noopener">Follow us on Facebook</a>
      </div>
      <div class="footer-col">
        <h4>Services</h4>
        <a href="/en/#residential">Residential</a>
        <a href="/en/commercial">Commercial</a>
        <a href="/en/commercial#after-construction">Post-construction</a>
        <a href="/en/#decapage">Floor stripping and waxing</a>
      </div>
      <div class="footer-col">
        <h4>Areas served</h4>
        <p>Montreal, Laval, Longueuil, the North Shore and the South Shore.</p>
      </div>
      <div class="footer-col">
        <h4>Contact</h4>
        <a href="tel:+15142424779">514 242-4779</a>
        <a href="mailto:contact@proline-cleaningsolutions.com">contact@proline-cleaningsolutions.com</a>
        <span class="note">Mon–Fri, 8am–6pm</span>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Proline Cleaning Solutions</span>
      <span><a href="/en">Home</a> · <a href="/en/soumission">Quote</a> · <a href="{alt}">Français</a></span>
      <span><a href="/en/privacy">Privacy</a> · <a href="/en/terms">Terms</a></span>
    </div>
  </div>
</footer>

<div class="callbar">
  <a class="btn btn-ghost" href="tel:+15142424779">Call</a>
  <a class="btn btn-primary" href="/en/soumission">Get a price</a>
</div>""",
}

SHELL = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Proline Cleaning Solutions</title>
<meta name="description" content="{description}">
<link rel="canonical" href="https://proline-cleaningsolutions.com{path}">
<link rel="alternate" hreflang="fr-ca" href="https://proline-cleaningsolutions.com{fr_path}">
<link rel="alternate" hreflang="en-ca" href="https://proline-cleaningsolutions.com{en_path}">
<link rel="alternate" hreflang="x-default" href="https://proline-cleaningsolutions.com{fr_path}">
<link rel="icon" href="/img/logo.png">
<meta property="og:type" content="website">
<meta property="og:locale" content="{og_locale}">
<meta property="og:title" content="{title} — Proline Cleaning Solutions">
<meta property="og:description" content="{description}">
<meta property="og:url" content="https://proline-cleaningsolutions.com{path}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Karla:wght@400;500;600&display=swap"
      media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Karla:wght@400;500;600&display=swap"></noscript>
<link rel="stylesheet" href="/css/app.css">
</head>
<body>
<div class="goldbar"></div>

<header class="site-header">
  <div class="container">
    <a class="brand" href="{home}">
      <img src="/img/logo.png" alt="" width="42" height="42">
      <span class="brand-text">
        <span class="brand-name">PROLINE</span>
        <span class="brand-sub">Cleaning Solutions</span>
      </span>
    </a>
{nav}
  </div>
</header>

<main>
  <section>
    <div class="container">
      <div class="legal">
        <div class="section-head">
          <span class="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p class="note">{updated}</p>
        </div>
{body}
      </div>
    </div>
  </section>
</main>

{footer}
</body>
</html>
"""


def section(heading, *blocks):
    out = ["        <h2>" + heading + "</h2>"]
    for b in blocks:
        if isinstance(b, list):
            out.append("        <ul>")
            out += ["          <li>" + item + "</li>" for item in b]
            out.append("        </ul>")
        else:
            out.append("        <p>" + b + "</p>")
    return "\n".join(out)


MAIL = '<a href="mailto:contact@proline-cleaningsolutions.com">contact@proline-cleaningsolutions.com</a>'

# --------------------------------------------------------------------------
# Confidentialité (FR)
# --------------------------------------------------------------------------
PRIVACY_FR = "\n\n".join([
    section("Qui est responsable de vos renseignements",
        "Proline Cleaning Solutions, entreprise de nettoyage établie dans le Grand Montréal, "
        "est responsable des renseignements personnels recueillis sur ce site. Toute question "
        "sur cette politique, ou toute demande concernant vos renseignements, se fait auprès du "
        "responsable de la protection des renseignements personnels à l'adresse " + MAIL + "."),

    section("Ce que nous recueillons",
        "Uniquement ce que vous inscrivez vous-même dans le formulaire de soumission, et rien de plus :",
        ["vos coordonnées : nom, entreprise le cas échéant, courriel, téléphone, moyen de contact préféré&nbsp;;",
         "l'adresse et la description du lieu : adresse, ville, quartier, code postal, superficie, "
         "nombre de pièces, d'étages ou de sanitaires&nbsp;;",
         "ce que vous demandez : services, fréquence, date souhaitée, notes d'accès&nbsp;;",
         "les photos que vous choisissez d'ajouter. Elles sont facultatives : le formulaire s'envoie "
         "et votre prix se calcule sans elles."],
        "S'y ajoute, quand vous arrivez par une publicité ou un lien suivi, la provenance de la visite "
        "(source, campagne, page d'arrivée). Elle sert à savoir quelles annonces valent leur coût et "
        "n'est associée à rien d'autre."),

    section("Pourquoi",
        "Pour établir votre prix, vous envoyer une soumission, et exécuter le service si vous "
        "l'acceptez. Vos photos servent à une seule chose : juger l'état des lieux pour chiffrer "
        "correctement, plutôt que de vous faire déplacer ou d'envoyer quelqu'un sur place."),

    section("Ce que nous ne faisons pas",
        ["nous ne vendons ni ne louons vos renseignements à personne&nbsp;;",
         "nous ne les utilisons pas pour du ciblage publicitaire&nbsp;;",
         "ce site ne dépose aucun témoin (cookie) et n'emploie aucun outil de mesure d'audience tiers&nbsp;;",
         "vos photos ne sont ni publiées, ni utilisées à des fins promotionnelles, ni montrées à "
         "quiconque en dehors des personnes qui préparent votre soumission."]),

    section("Combien de temps nous les gardons",
        ["<strong>Les photos sont supprimées automatiquement après un an.</strong> Ce n'est pas une "
         "intention : une tâche programmée les efface du disque et de la base de données chaque jour, "
         "qu'on y pense ou non&nbsp;;",
         "votre demande de soumission et les échanges qui s'y rattachent sont conservés le temps de la "
         "relation d'affaires, puis pour la durée où la loi nous oblige à garder nos pièces comptables&nbsp;;",
         "vous pouvez demander la suppression de vos renseignements avant ces délais (voir plus bas)."]),

    section("Où ils se trouvent",
        "Sur des serveurs d'Amazon Web Services situés au Canada, dans la région <em>ca-central-1</em>. "
        "Les courriels que nous vous envoyons partent d'Amazon SES, dans la même région canadienne. "
        "Vos renseignements ne sont pas hébergés à l'extérieur du Canada."),

    section("Ce que votre navigateur garde, chez vous",
        "Pour que vous puissiez quitter le formulaire et y revenir sans tout ressaisir, votre navigateur "
        "conserve localement le brouillon de vos réponses et la provenance de votre visite. "
        "Ce ne sont pas des témoins : rien de tout cela ne nous est transmis avant que vous n'appuyiez "
        "sur envoyer, et vider les données de site de votre navigateur les efface."),

    section("Vos droits",
        "Vous pouvez à tout moment&nbsp;:",
        ["consulter les renseignements que nous détenons sur vous&nbsp;;",
         "les faire corriger s'ils sont inexacts ou incomplets&nbsp;;",
         "en demander la suppression, y compris vos photos, avant l'échéance prévue&nbsp;;",
         "retirer votre consentement, ce qui met fin à l'utilisation de vos renseignements pour la suite."],
        "Écrivez à " + MAIL + " et nous répondons dans les 30 jours. Si notre réponse ne vous satisfait "
        "pas, vous pouvez vous adresser à la Commission d'accès à l'information du Québec."),

    section("Modifications",
        "Si cette politique change, la date en haut de la page change avec elle. Un changement qui "
        "touche l'usage de renseignements déjà recueillis vous est signalé directement."),
])

PRIVACY_EN = "\n\n".join([
    section("Who is responsible for your information",
        "Proline Cleaning Solutions, a cleaning company serving Greater Montreal, is responsible for "
        "the personal information collected through this site. Any question about this policy, or any "
        "request concerning your information, goes to the person responsible for the protection of "
        "personal information at " + MAIL + "."),

    section("What we collect",
        "Only what you enter in the quote form yourself, and nothing beyond it:",
        ["your contact details: name, company if any, email, telephone, preferred way to reach you;",
         "the address and description of the place: address, city, borough, postal code, area, number "
         "of rooms, floors or washrooms;",
         "what you are asking for: services, frequency, preferred start date, access notes;",
         "any photos you choose to add. They are optional: the form sends and your price is calculated "
         "without them."],
        "Where you arrive from an advertisement or a tracked link, we also record the origin of the "
        "visit (source, campaign, landing page). It tells us which ads are worth their cost and is "
        "linked to nothing else."),

    section("Why",
        "To work out your price, send you a quote, and carry out the work if you accept it. Your photos "
        "serve one purpose: judging the state of the place so it can be priced properly, instead of "
        "making you wait for a site visit."),

    section("What we do not do",
        ["we do not sell or rent your information to anyone;",
         "we do not use it for advertising targeting;",
         "this site sets no cookies and uses no third-party analytics;",
         "your photos are never published, never used for promotion, and never shown to anyone outside "
         "the people preparing your quote."]),

    section("How long we keep it",
        ["<strong>Photos are deleted automatically after one year.</strong> Not as an intention: a "
         "scheduled job erases them from disk and from the database every day, whether or not anyone "
         "remembers it exists;",
         "your quote request and the exchanges attached to it are kept for the duration of the business "
         "relationship, and then for as long as the law requires us to keep accounting records;",
         "you can ask us to delete your information before those periods end (see below)."]),

    section("Where it is held",
        "On Amazon Web Services servers located in Canada, in the <em>ca-central-1</em> region. The "
        "emails we send you go out through Amazon SES in that same Canadian region. Your information is "
        "not hosted outside Canada."),

    section("What your browser keeps, on your own device",
        "So that you can leave the form and come back without retyping everything, your browser keeps a "
        "local draft of your answers and the origin of your visit. These are not cookies: none of it "
        "reaches us before you press send, and clearing your browser's site data erases it."),

    section("Your rights",
        "At any time you may:",
        ["see the information we hold about you;",
         "have it corrected if it is inaccurate or incomplete;",
         "ask for it to be deleted, photos included, before the periods above have run;",
         "withdraw your consent, which ends our use of your information from that point on."],
        "Write to " + MAIL + " and we answer within 30 days. If our answer does not satisfy you, you may "
        "take the matter to the Commission d'accès à l'information du Québec."),

    section("Changes",
        "If this policy changes, the date at the top of the page changes with it. A change affecting how "
        "information already collected is used will be communicated to you directly."),
])

# --------------------------------------------------------------------------
# Conditions (FR / EN)
# --------------------------------------------------------------------------
TERMS_FR = "\n\n".join([
    section("À propos de ces conditions",
        "Elles s'appliquent aux services d'entretien rendus par Proline Cleaning Solutions et aux "
        "demandes faites par ce site. Une soumission acceptée les complète&nbsp;: en cas de divergence, "
        "c'est ce qui est écrit sur votre soumission qui prévaut."),

    section("Le prix affiché en ligne",
        "Pour un logement standard, le prix calculé à l'écran est ferme. Il suppose un logement en état "
        "d'usage normal et un accès sans difficulté particulière.",
        "Nous vous en informons avant la première visite, et jamais après coup, si les lieux diffèrent "
        "sensiblement de ce qui a été décrit&nbsp;: superficie très différente, encombrement important, "
        "dégâts, chantier en cours. Vous décidez alors de poursuivre au prix révisé ou d'annuler sans frais.",
        "Les demandes commerciales ne sont pas chiffrées en ligne. Elles reçoivent une soumission écrite "
        "sous 24 heures ouvrables."),

    section("Rendez-vous et annulation",
        "Vous pouvez annuler ou déplacer une visite sans frais jusqu'à 24 heures avant l'heure prévue. "
        "En deçà, ou si l'équipe se présente et ne peut pas entrer, la visite peut être facturée.",
        "Si nous devons annuler, nous vous proposons la première date disponible et la visite n'est pas facturée."),

    section("Accès aux lieux",
        "Vous nous donnez le moyen d'entrer&nbsp;: quelqu'un sur place, un code, une clé ou une consigne "
        "auprès de la conciergerie. Les consignes que vous nous transmettez sont conservées à votre dossier "
        "et communiquées à la seule équipe qui dessert votre adresse.",
        "Prévenez-nous des objets fragiles ou de valeur et des pièces à ne pas nettoyer. Ce qui est signalé "
        "à l'avance est respecté."),

    section("Satisfaction garantie ou reprise",
        "Si une partie du travail ne vous satisfait pas, dites-le dans les 24 heures suivant la visite. "
        "Nous revenons reprendre la zone concernée sans frais. C'est une reprise du travail&nbsp;; elle ne "
        "constitue pas un remboursement automatique."),

    section("Produits, équipement et personnel",
        "Les produits et l'équipement sont fournis, sauf entente contraire écrite. Le personnel est en "
        "uniforme et identifiable dès l'arrivée. L'entreprise détient une assurance responsabilité et un "
        "cautionnement&nbsp;; une attestation vous est remise sur demande."),

    section("Paiement",
        "Les modalités et les délais de paiement sont indiqués sur votre soumission ou votre facture. "
        "Les taxes applicables s'ajoutent aux montants affichés."),

    section("Limites",
        "Certains travaux sortent de l'entretien ménager et font l'objet d'une entente distincte&nbsp;: "
        "dégâts d'eau, moisissure, nuisibles, matières dangereuses, travaux en hauteur. Nous vous le "
        "disons plutôt que de les improviser.",
        "Nous ne répondons pas de l'usure normale ni des dommages préexistants. Un dommage causé par notre "
        "équipe doit nous être signalé dans les 48 heures pour être traité."),

    section("Droit applicable",
        "Ces conditions sont régies par les lois en vigueur au Québec. Les renseignements que vous nous "
        "confiez sont traités selon notre <a href=\"/confidentialite\">politique de confidentialité</a>."),
])

TERMS_EN = "\n\n".join([
    section("About these terms",
        "They apply to the cleaning services provided by Proline Cleaning Solutions and to requests made "
        "through this site. An accepted quote adds to them: where the two differ, what is written on your "
        "quote prevails."),

    section("The price shown online",
        "For a standard home, the price calculated on screen is firm. It assumes a home in ordinary "
        "condition and access without particular difficulty.",
        "We tell you before the first visit, and never afterwards, if the place differs substantially from "
        "what was described: a very different area, heavy clutter, damage, work in progress. You then "
        "decide whether to go ahead at the revised price or cancel at no cost.",
        "Commercial requests are not priced online. They receive a written quote within 24 business hours."),

    section("Appointments and cancellation",
        "You may cancel or move a visit at no cost up to 24 hours before the scheduled time. Later than "
        "that, or if the team arrives and cannot get in, the visit may be charged.",
        "If we have to cancel, we offer you the first available date and the visit is not charged."),

    section("Access to the premises",
        "You give us a way in: someone on site, a code, a key, or an instruction left with the concierge. "
        "The instructions you give us are kept on your file and passed only to the team that serves your "
        "address.",
        "Tell us about fragile or valuable items and any rooms not to be cleaned. What is flagged in "
        "advance is respected."),

    section("Satisfaction guaranteed or we come back",
        "If part of the work does not satisfy you, tell us within 24 hours of the visit. We return and "
        "redo the area concerned at no charge. This is a redo of the work; it is not an automatic refund."),

    section("Products, equipment and staff",
        "Products and equipment are supplied unless agreed otherwise in writing. Staff are in uniform and "
        "identifiable on arrival. The company carries liability insurance and is bonded; a certificate is "
        "provided on request."),

    section("Payment",
        "Payment terms and deadlines are stated on your quote or invoice. Applicable taxes are added to "
        "the amounts shown."),

    section("Limits",
        "Some work falls outside housekeeping and is the subject of a separate agreement: water damage, "
        "mould, pests, hazardous materials, work at height. We say so rather than improvise it.",
        "We are not responsible for normal wear or for pre-existing damage. Damage caused by our team must "
        "be reported to us within 48 hours to be dealt with."),

    section("Governing law",
        "These terms are governed by the laws in force in Quebec. Information you give us is handled "
        "according to our <a href=\"/en/privacy\">privacy policy</a>."),
])

UPDATED_FR = "Dernière mise à jour : 26 septembre 2026"
UPDATED_EN = "Last updated: 26 September 2026"

PAGES = [
    dict(out="confidentialite.html", lang="fr", og_locale="fr_CA", home="/",
         path="/confidentialite", fr_path="/confidentialite", en_path="/en/privacy",
         alt="/en/privacy", eyebrow="Vie privée", title="Politique de confidentialité",
         description="Ce que Proline Cleaning Solutions recueille, pourquoi, combien de temps, et comment "
                     "faire supprimer vos renseignements. Photos supprimées après un an.",
         updated=UPDATED_FR, body=PRIVACY_FR),
    dict(out="conditions.html", lang="fr", og_locale="fr_CA", home="/",
         path="/conditions", fr_path="/conditions", en_path="/en/terms",
         alt="/en/terms", eyebrow="Conditions", title="Conditions de service",
         description="Prix, annulation, accès aux lieux et garantie de reprise pour les services "
                     "d'entretien de Proline Cleaning Solutions.",
         updated=UPDATED_FR, body=TERMS_FR),
    dict(out="en/privacy.html", lang="en", og_locale="en_CA", home="/en",
         path="/en/privacy", fr_path="/confidentialite", en_path="/en/privacy",
         alt="/confidentialite", eyebrow="Privacy", title="Privacy policy",
         description="What Proline Cleaning Solutions collects, why, for how long, and how to have your "
                     "information deleted. Photos deleted after one year.",
         updated=UPDATED_EN, body=PRIVACY_EN),
    dict(out="en/terms.html", lang="en", og_locale="en_CA", home="/en",
         path="/en/terms", fr_path="/conditions", en_path="/en/terms",
         alt="/conditions", eyebrow="Terms", title="Terms of service",
         description="Pricing, cancellation, access and the redo guarantee for cleaning services from "
                     "Proline Cleaning Solutions.",
         updated=UPDATED_EN, body=TERMS_EN),
]


def main() -> None:
    for page in PAGES:
        lang = page["lang"]
        html = SHELL.format(
            nav=NAV[lang].format(alt=page["alt"]),
            footer=FOOTER[lang].format(alt=page["alt"]),
            **{k: v for k, v in page.items() if k != "out"},
        )
        target = HERE / page["out"]
        target.write_text(html)
        print("wrote", target.relative_to(HERE.parent))


if __name__ == "__main__":
    main()
