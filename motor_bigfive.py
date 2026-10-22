"""Indicadores textuales reproducibles, no evaluaciones psicometricas.

RULES describe frases admitidas y su direccion textual. Una coincidencia no
demuestra un rasgo ni identifica a la persona propietaria de una cuenta.
"""

import re
import unicodedata


ENGINE_VERSION = "heuristica_v1"
DIMENSIONS = {
    "apertura": "Apertura a la experiencia",
    "responsabilidad": "Responsabilidad",
    "extraversion": "Extraversión",
    "amabilidad": "Amabilidad",
    "neuroticismo": "Neuroticismo",
}
DESCRIPTIONS = {
    "apertura": "Expresiones de curiosidad o preferencia por lo conocido.",
    "responsabilidad": "Expresiones de organizacion o desorganizacion habitual.",
    "extraversion": "Preferencias expresadas por la interaccion o la soledad.",
    "amabilidad": "Expresiones de cooperacion o trato poco considerado.",
    "neuroticismo": "Expresiones de preocupacion recurrente o estabilidad emocional.",
}


def empty_results(method=ENGINE_VERSION, explanation="Sin evidencia suficiente."):
    """Devuelve cinco abstenciones independientes y en orden estable."""
    return [
        {
            "dimension": dimension,
            "senal": False,
            "direccion": "no_interpretable",
            "evidencia": [],
            "explicacion": explanation,
            "metodo": method,
            "estado": "sin evidencia suficiente",
            "referencia": "irrelevante",
        }
        for dimension in DIMENSIONS
    ]


def _normalize(text):
    """Normaliza para buscar, conservando intervalos en el texto original."""
    chars, offsets = [], []
    for index, original in enumerate(text):
        normalized = "".join(
            char for char in unicodedata.normalize("NFD", original.lower())
            if not unicodedata.combining(char)
        )
        if not normalized and unicodedata.combining(original):
            if offsets:
                offsets[-1] = (offsets[-1][0], index + 1)
            continue
        for char in normalized:
            char = " " if char.isspace() else char
            if char == " " and chars and chars[-1] == " ":
                offsets[-1] = (offsets[-1][0], index + 1)
            else:
                chars.append(char)
                offsets.append((index, index + 1))
    return "".join(chars), offsets


_REFERENCE = (
    r"soy|me considero|me describo como|eres|te considero|"
    r"pareces(?: ser)?(?: una persona)?|"
    r"parece(?: ser)? (?:una persona|alguien)|es una persona|"
    r"el es|ella es|i am|i'm|you are|you're|he is|she is|they are"
)
_ADJECTIVE_START = (
    r"(?<!\w)(?P<before>no\s+)?(?P<reference>" + _REFERENCE + r")\s+"
    r"(?P<after>not\s+)?(?:(?:muy|bastante|realmente|very|really)\s+)?"
)

# Direccion positiva/negativa = polo alto/bajo del rasgo, no sentimiento ni
# valoracion moral. Los fragmentos de bio requieren contexto linguistico adicional.
_ADJECTIVES = {
    "apertura": (
        r"creativ[oa]|curios[oa]|de mente abierta|creative|curious|open[- ]minded",
        r"de costumbres fijas|poco curios[oa]|cerrad[oa] a nuevas experiencias|closed[- ]minded",
    ),
    "responsabilidad": (
        r"organizad[oa]|responsable|disciplinad[oa]|metodic[oa]|organized|organised|conscientious|disciplined",
        r"desorganizad[oa]|irresponsable|descuidad[oa]|disorganized|disorganised|careless",
    ),
    "extraversion": (
        r"sociable|extrovertid[oa]|extravertid[oa]|outgoing|extroverted|sociable",
        r"introvertid[oa]|reservad[oa]|poco sociable|introverted|reserved",
    ),
    "amabilidad": (
        r"amable|empatic[oa]|considerad[oa]|cooperativ[oa]|kind|empathetic|considerate|cooperative",
        r"poco empatic[oa]|desconsiderad[oa]|hostil con los demas|inconsiderate|uncooperative",
    ),
    "neuroticismo": (
        r"emocionalmente inestable|emotional(?:ly)? unstable",
        r"emocionalmente estable|emocionalmente tranquil[oa]|emotionally stable|emotionally calm",
    ),
}


def _make_rules():
    rules = []
    for dimension, poles in _ADJECTIVES.items():
        for direction, adjectives in zip(("positiva", "negativa"), poles):
            rules.append({
                "dimension": dimension,
                "direccion": direction,
                "patron": _ADJECTIVE_START + r"(?:" + adjectives + r")(?!\w)",
                "tipo": "personal",
            })
            rules.append({
                "dimension": dimension,
                "direccion": direction,
                "patron": (
                    r"(?:^|[,;|/]|\by\b|\band\b)\s*(?P<before>no\s+|not\s+)?"
                    r"(?:" + adjectives + r")(?=\s*(?:$|[,;|/]|\by\b|\band\b))"
                ),
                "tipo": "biografia",
            })
    phrases = (
        ("apertura", "positiva", r"(?:me gusta|me encanta|disfruto) (?:mucho )?(?:aprender cosas nuevas|explorar nuevas ideas|probar cosas nuevas|conocer otras culturas)"),
        ("apertura", "negativa", r"prefiero (?:seguir siempre la misma rutina|lo conocido a lo nuevo)|evito (?:probar cosas nuevas|las nuevas experiencias)"),
        ("responsabilidad", "positiva", r"siempre (?:planifico mis tareas|cumplo mis compromisos|cumplo mis promesas|organizo mis tareas)|me gusta (?:planificar mis tareas|tener todo organizado)"),
        ("responsabilidad", "negativa", r"siempre (?:dejo todo para el ultimo momento|incumplo mis compromisos|pierdo mis cosas)|suelo (?:dejar todo para el ultimo momento|olvidar mis compromisos)"),
        ("extraversion", "positiva", r"(?:me encanta|me gusta|disfruto) (?:mucho )?(?:conocer gente nueva|conversar con todos|estar rodead[oa] de gente|socializar)"),
        ("extraversion", "negativa", r"prefiero (?:estar sol[oa]|pasar tiempo a solas)|evito (?:las reuniones sociales|socializar)"),
        ("amabilidad", "positiva", r"(?:me gusta|me encanta|disfruto) (?:ayudar a los demas|cooperar con los demas|escuchar a los demas)|siempre (?:trato a los demas con respeto|intento comprender a los demas)"),
        ("amabilidad", "negativa", r"(?:no me importa|me da igual) (?:como se sienten los demas|el bienestar de los demas)|suelo (?:tratar mal a los demas|burlarme de los demas)"),
        ("neuroticismo", "positiva", r"me preocupo (?:por todo|constantemente|todo el tiempo)|siempre (?:me preocupo por todo|estoy preocupad[oa] por todo)|mis emociones cambian constantemente"),
        ("neuroticismo", "negativa", r"suelo mantener la calma (?:bajo presion|ante los problemas)|mantengo la calma (?:bajo presion|ante los problemas)|rara vez me preocupo"),
        ("apertura", "positiva", r"i (?:enjoy|love|like) (?:learning new things|exploring new ideas|trying new things)"),
        ("apertura", "negativa", r"i prefer (?:familiar routines|the familiar to the new)|i avoid new experiences"),
        ("responsabilidad", "positiva", r"i always (?:plan my tasks|keep my promises|meet my deadlines)|i like to plan ahead"),
        ("responsabilidad", "negativa", r"i always (?:leave things until the last minute|miss my deadlines|lose my things)|i often forget my commitments"),
        ("extraversion", "positiva", r"i (?:enjoy|love|like) (?:meeting new people|talking to everyone|socializing)|i like to meet new people"),
        ("extraversion", "negativa", r"i prefer (?:being alone|spending time alone)|i avoid social gatherings"),
        ("amabilidad", "positiva", r"i (?:enjoy|love|like) helping others|i always treat others with respect"),
        ("amabilidad", "negativa", r"i don't care about (?:other people's feelings|others)|i often treat others badly"),
        ("neuroticismo", "positiva", r"i (?:always|constantly) worry(?: about everything)?|i worry (?:about everything|all the time)|my emotions constantly change"),
        ("neuroticismo", "negativa", r"i (?:usually )?stay calm under pressure|i rarely worry"),
    )
    for dimension, direction, phrase in phrases:
        rules.append({
            "dimension": dimension,
            "direccion": direction,
            "patron": r"(?<!\w)(?P<before>no\s+)?(?:" + phrase + r")(?!\w)",
            "tipo": "personal",
        })
    return tuple(rules)


RULES = _make_rules()
_COMPILED_RULES = tuple((rule, re.compile(rule["patron"])) for rule in RULES)
_THIRD_PERSON = re.compile(
    r"^(?:eres|te considero|pareces|parece|es una persona|el es|ella es|"
    r"you are|you're|he is|she is|they are)\b"
)
_AMBIGUOUS = re.compile(
    r"\b(?:no solo|no solamente|not only|sin duda|no es que|"
    r"no creo que|no digo que|no parece que)\b|"
    r"\b(?:no|not|never|nunca)\s+(?:(?:yo|i|really)\s+)?(?:no|not|never|nunca)\b"
)
_IRONY = re.compile(r"\b(?:sarcasmo|sarcasm|ironia|ironicamente|yeah right)\b|/s\b|[\U0001f644\U0001f609]")
_TRANSIENT = re.compile(r"\b(?:hoy|ahora|en este momento|ultimamente|today|right now|at the moment)\b")
_NON_TEXT = re.compile(r"(?:https?://|www\.)\S+|(?<!\w)[#@]\w+")
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_REPORTED = re.compile(
    r"\b(?:me (?:dijeron|dicen|dijo)|(?:dice|dicen|dijo|dijeron) que|"
    r"segun|they (?:say|said)|(?:he|she) (?:says|said)|i was told)\b"
)
_QUOTED = re.compile(r'''"[^"]*"|“[^”]*”|«[^»]*»|(?<!\w)'[^']*'(?!\w)''')


class HeuristicEngine:
    """Analiza lo dicho, sin inferir personalidad ni ofrecer confianza numerica."""

    method = ENGINE_VERSION

    def analyze(self, text, source="comentario"):
        results = empty_results(self.method)
        if not isinstance(text, str) or not text.strip():
            return results
        if not isinstance(source, str) or source not in ("comentario", "biografia"):
            return results
        normalized, offsets = _normalize(text)
        excluded = [match.span() for match in _NON_TEXT.finditer(normalized)]
        if source == "biografia":
            words = [word for word in _WORDS.findall(_NON_TEXT.sub(" ", normalized))
                     if word not in {"y", "and", "o", "or"}]
            if len(words) < 2:
                return results
        quoted = [match.span() for match in _QUOTED.finditer(normalized)]
        found = {dimension: [] for dimension in DIMENSIONS}
        for rule, pattern in _COMPILED_RULES:
            if rule["tipo"] == "biografia" and source != "biografia":
                continue
            for match in pattern.finditer(normalized):
                if any(match.start() < end and match.end() > start for start, end in excluded):
                    continue
                if any(match.start() < end and match.end() > start for start, end in quoted):
                    continue
                # El discurso referido no equivale a una afirmacion propia.
                sentence_left = max(normalized.rfind(mark, 0, match.start()) for mark in ".!?;") + 1
                if _REPORTED.search(normalized[sentence_left:match.start()]):
                    continue
                # Conservador ante ambitos de negacion o estados temporales:
                # se examina la clausula, no se invierte por palabras lejanas.
                left = max(normalized.rfind(mark, 0, match.start()) for mark in ".!?;,") + 1
                right_matches = [normalized.find(mark, match.end()) for mark in ".!?;,"]
                right = min((pos for pos in right_matches if pos >= 0), default=len(normalized))
                context = normalized[left:right]
                if '?' in normalized[left:min(right + 1, len(normalized))] or '\u00bf' in context:
                    continue
                prefix = normalized[left:match.start()]
                groups = match.groupdict()
                negated = bool(groups.get("before") or groups.get("after"))
                if _AMBIGUOUS.search(context) or _TRANSIENT.search(context):
                    continue
                if (groups.get("before") and groups.get("after")) or (
                    negated and re.search(r"\b(?:poco|nunca|never)\b", match.group())
                ):
                    continue
                if re.search(r"\b(?:no|not|nunca|never|don't|do not)\s*$", prefix):
                    continue
                if re.search(r"\b(?:el video|este video|the video)\b", context):
                    continue
                direction = rule["direccion"]
                if negated:
                    direction = "negativa" if direction == "positiva" else "positiva"
                reference = groups.get("reference") or ""
                if _THIRD_PERSON.search(reference):
                    reference = "percepcion_tercero"
                elif source == "biografia":
                    reference = "autopresentacion"
                else:
                    reference = "autorreferencia"
                start, end = match.span()
                # La cita de una lista conserva el contexto que habilito la senal.
                if rule["tipo"] == "biografia":
                    start = len(normalized) - len(normalized.lstrip())
                    end = len(normalized.rstrip())
                quote = text[offsets[start][0]:offsets[end - 1][1]]
                found[rule["dimension"]].append((start, direction, quote, reference))

        for result in results:
            evidence = sorted(set(found[result["dimension"]]))
            if not evidence:
                if re.search(r"\b(?:video|clip)\b", normalized):
                    result["referencia"] = "opinion_video"
                continue
            directions = {item[1] for item in evidence}
            references = {item[3] for item in evidence}
            # El contrato no permite separar sujetos en una misma dimension.
            if len(references) > 1:
                result["explicacion"] = "Referencias a sujetos distintos; no se agregan como una sola persona."
                continue
            reference = evidence[0][3]
            explanation = (
                "Indicador textual por coincidencia de frases publicas; no es una "
                "evaluacion psicometrica ni demuestra personalidad."
            )
            if reference == "percepcion_tercero":
                explanation += " Describe una percepcion de un tercero, no la personalidad del dueno de la cuenta."
            if len(directions) > 1:
                explanation += " Hay expresiones de ambos polos; la direccion textual es mixta."
            if _IRONY.search(normalized):
                explanation += " Posible ironia o sarcasmo: la heuristica no puede resolver la intencion literal."
            result.update({
                "senal": True,
                "direccion": "mixta" if len(directions) > 1 else evidence[0][1],
                "evidencia": list(dict.fromkeys(item[2] for item in evidence)),
                "explicacion": explanation,
                "estado": "senal_identificada",
                "referencia": reference,
            })
        return results
