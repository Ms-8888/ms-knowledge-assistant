"""The 10-question test used to choose the embedding model and the 0.28 threshold.

Run before the 38-question evaluation was written; the evaluation was not used to tune either choice.
Needs `pip install fastembed`. Prints top-1 hits and similarity scores for three multilingual models.
"""
import time, numpy as np
from fastembed import TextEmbedding
P = [
 "Vakantiedagen: elke medewerker heeft recht op 25 vakantiedagen per jaar. Aanvragen gaan via het HR-portaal minstens twee weken vooraf.",
 "Thuiswerken is toegestaan tot drie dagen per week, in overleg met de teamleider. Een thuiswerkvergoeding van 20 euro per maand wordt uitbetaald.",
 "Bij ziekte verwittig je je teamleider vóór 9 uur. Na drie dagen afwezigheid is een doktersbriefje verplicht.",
 "Onkosten worden terugbetaald na het indienen van een bonnetje in de onkostentool. Maaltijden tot 25 euro per dag zijn toegestaan.",
 "De bedrijfswagen mag ook privé gebruikt worden. Tankkosten voor privégebruik worden niet vergoed.",
 "Nieuwe medewerkers krijgen op de eerste dag een laptop, een badge en een rondleiding. De eerste maand is een proefperiode met wekelijkse feedback.",
 "Wachtwoorden moeten minstens 14 tekens bevatten en worden elk jaar vernieuwd. Deel nooit je wachtwoord met collega's.",
 "Opleidingen: elk jaar is er een budget van 1000 euro per medewerker voor cursussen of conferenties, goed te keuren door de manager.",
 "Klachten van klanten worden binnen 24 uur bevestigd en binnen vijf werkdagen opgelost. Escaleer naar de supportmanager bij een ernstige klacht.",
 "Het bedrijf sluit tussen Kerstmis en Nieuwjaar. Deze dagen tellen niet mee als vakantiedagen.",
]
Q = [("Hoeveel verlofdagen heb ik per jaar?",0),("Mag ik van thuis uit werken?",1),("Wat moet ik doen als ik ziek ben?",2),
     ("Hoe krijg ik mijn onkosten terug?",3),("Wie betaalt de benzine van de firmawagen voor privé?",4),("Wat gebeurt er mijn eerste werkdag?",5),
     ("Hoe lang moet een paswoord zijn?",6),("Is er een budget voor cursussen?",7),("Binnen welke termijn lossen jullie klachten op?",8),("Is het bedrijf gesloten rond de feestdagen?",9)]
for name in ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2","sentence-transformers/paraphrase-multilingual-mpnet-base-v2","minishlab/potion-multilingual-128M"]:
    t=time.time(); m=TextEmbedding(name); load=time.time()-t
    t=time.time(); pe=np.array(list(m.embed(P))); qe=np.array(list(m.embed([q for q,_ in Q]))); enc=time.time()-t
    pe/=np.linalg.norm(pe,axis=1,keepdims=True); qe/=np.linalg.norm(qe,axis=1,keepdims=True)
    S=qe@pe.T; top1=sum(int(S[i].argmax()==a) for i,(_,a) in enumerate(Q))
    top = [float(S[i,a]) for i,(_,a) in enumerate(Q)]
    print(f"{name.split('/')[1]}: top1 {top1}/10 | load+download {load:.0f}s | encode 20 texts {enc:.2f}s | mean sim of right passage {np.mean(top):.2f} | wrong-best mean {np.mean([S[i].max() for i in range(10)]):.2f}")


# Second part: how far apart are in-scope and off-topic questions? This is what the 0.28
# threshold was read from (in-scope minimum 0.35 vs off-topic maximum 0.21 for MiniLM).
OFF_TOPIC = [
    "Wat is de hoofdstad van Frankrijk?",
    "Hoe bak ik een pannenkoek?",
    "Wie won het WK voetbal in 2018?",
    "Hoe werkt een kernreactor?",
    "Wat is het weer morgen in Antwerpen?",
    "Wat is de beste programmeertaal?",
]
for name in [
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
]:
    model = TextEmbedding(name)

    def unit(vectors):
        array = np.array(list(vectors))
        return array / np.linalg.norm(array, axis=1, keepdims=True)

    passages = unit(model.embed(P))
    in_scope = (unit(model.embed([q for q, _ in Q])) @ passages.T).max(1)
    off_topic = (unit(model.embed(OFF_TOPIC)) @ passages.T).max(1)
    print(
        f"{name.split('/')[1]}: in-scope max-sim min {in_scope.min():.2f} mean {in_scope.mean():.2f}"
        f" | off-topic max-sim mean {off_topic.mean():.2f} max {off_topic.max():.2f}"
    )
