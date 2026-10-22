"""Contrato y limites de un motor local de indicadores, no de psicometria."""

import socket
import unittest
from unittest.mock import patch

from motor_bigfive import DIMENSIONS, ENGINE_VERSION, RULES, HeuristicEngine, empty_results


class HeuristicEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = HeuristicEngine()

    def dimension(self, text, dimension, source="comentario"):
        results = self.engine.analyze(text, source)
        for result in results:
            for quote in result["evidencia"]:
                self.assertIn(quote, text)
        return next(result for result in results if result["dimension"] == dimension)

    def assert_abstains(self, text, source="comentario"):
        results = self.engine.analyze(text, source)
        self.assertEqual(len(results), 5)
        for result in results:
            self.assertFalse(result["senal"])
            self.assertEqual(result["direccion"], "no_interpretable")
            self.assertEqual(result["evidencia"], [])
            self.assertEqual(result["estado"], "sin evidencia suficiente")

    def test_contract_and_order(self):
        self.assertEqual(list(DIMENSIONS), ["apertura", "responsabilidad", "extraversion", "amabilidad", "neuroticismo"])
        self.assertEqual(ENGINE_VERSION, "heuristica_v1")
        self.assertEqual(self.engine.method, ENGINE_VERSION)
        results = self.engine.analyze("Soy sociable")
        self.assertEqual([item["dimension"] for item in results], list(DIMENSIONS))
        keys = {"dimension", "senal", "direccion", "evidencia", "explicacion", "metodo", "estado", "referencia"}
        for result in results:
            self.assertEqual(set(result), keys)
            self.assertIs(type(result["senal"]), bool)
            self.assertEqual(result["metodo"], ENGINE_VERSION)

    def test_empty_results_are_independent(self):
        results = empty_results("custom", "Nada.")
        results[0]["evidencia"].append("test")
        self.assertEqual(results[1]["evidencia"], [])
        self.assertEqual(empty_results()[0]["evidencia"], [])
        self.assertTrue(all(item["metodo"] == "custom" for item in results))
        self.assertTrue(all(item["explicacion"] == "Nada." for item in results))

    def test_public_rules(self):
        self.assertTrue(RULES)
        self.assertTrue(all(rule["dimension"] in DIMENSIONS and rule["patron"] for rule in RULES))

    def test_required_social_example(self):
        text = "Me encanta conocer gente nueva y conversar con todos"
        result = self.dimension(text, "extraversion")
        self.assertTrue(result["senal"])
        self.assertEqual(result["direccion"], "positiva")
        self.assertEqual(result["referencia"], "autorreferencia")

    def test_third_person_is_not_account_owner(self):
        result = self.dimension("Parece una persona muy sociable", "extraversion")
        self.assertTrue(result["senal"])
        self.assertEqual(result["referencia"], "percepcion_tercero")
        self.assertIn("no la personalidad del dueno", result["explicacion"])

    def test_second_person(self):
        self.assertEqual(self.dimension("Eres muy amable", "amabilidad")["referencia"], "percepcion_tercero")

    def test_good_video(self):
        self.assert_abstains("Buen video")
        self.assertTrue(all(result["referencia"] == "opinion_video" for result in self.engine.analyze("Buen video")))

    def test_questions_are_not_personal_assertions(self):
        for text in ('\u00bfEres sociable?', 'Soy creativo?', 'You are outgoing?'):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_video_creativity_is_not_openness(self):
        self.assert_abstains("El video es creativo y muy original")

    def test_today_sad_is_not_neuroticism(self):
        self.assert_abstains("Hoy estoy triste")

    def test_emotions_alone_are_not_traits(self):
        for text in ("Estoy feliz", "Tengo miedo", "Estoy triste", "I am sad", "I feel anxious today", "Me encanta este video"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_transient_trait_description_abstains(self):
        for text in ("Hoy soy sociable", "Hoy me preocupo por todo", "I am outgoing today"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_all_dimensions_both_poles_spanish(self):
        cases = {
            "apertura": ("Soy creativa", "Prefiero lo conocido a lo nuevo"),
            "responsabilidad": ("Siempre cumplo mis compromisos", "Soy desorganizado"),
            "extraversion": ("Soy sociable", "Prefiero estar solo"),
            "amabilidad": ("Me gusta ayudar a los demás", "Soy desconsiderada"),
            "neuroticismo": ("Me preocupo por todo", "Soy emocionalmente estable"),
        }
        for dimension, texts in cases.items():
            for text, direction in zip(texts, ("positiva", "negativa")):
                with self.subTest(text=text):
                    result = self.dimension(text, dimension)
                    self.assertTrue(result["senal"])
                    self.assertEqual(result["direccion"], direction)

    def test_all_dimensions_both_poles_english(self):
        cases = {
            "apertura": ("I enjoy learning new things", "I prefer familiar routines"),
            "responsabilidad": ("I always keep my promises", "I am disorganized"),
            "extraversion": ("I am outgoing", "I prefer being alone"),
            "amabilidad": ("I enjoy helping others", "I am inconsiderate"),
            "neuroticismo": ("I constantly worry about everything", "I stay calm under pressure"),
        }
        for dimension, texts in cases.items():
            for text, direction in zip(texts, ("positiva", "negativa")):
                with self.subTest(text=text):
                    self.assertEqual(self.dimension(text, dimension)["direccion"], direction)

    def test_spanish_adjective_negation(self):
        result = self.dimension("No soy sociable", "extraversion")
        self.assertEqual(result["direccion"], "negativa")
        self.assertEqual(result["evidencia"], ["No soy sociable"])

    def test_spanish_preference_negation(self):
        result = self.dimension("No me gusta conocer gente nueva", "extraversion")
        self.assertEqual(result["direccion"], "negativa")
        self.assertEqual(result["evidencia"], ["No me gusta conocer gente nueva"])

    def test_english_adjective_negation(self):
        result = self.dimension("I am not outgoing", "extraversion")
        self.assertEqual(result["direccion"], "negativa")
        self.assertEqual(result["evidencia"], ["I am not outgoing"])

    def test_unsupported_english_negation_is_not_positive(self):
        for text in ("I do not enjoy meeting new people", "I don't enjoy meeting new people"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_ambiguous_negation_abstains(self):
        for text in ("No no soy sociable", "No solo soy sociable", "No soy poco sociable", "No es que no soy sociable", "No creo que soy sociable", "I am not not outgoing", "I am not only outgoing", "Sin duda soy sociable"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_negative_trait_can_be_negated(self):
        self.assertEqual(self.dimension("No soy desorganizada", "responsabilidad")["direccion"], "positiva")

    def test_contradiction_has_both_quotes(self):
        result = self.dimension("Soy sociable pero prefiero estar solo", "extraversion")
        self.assertEqual(result["direccion"], "mixta")
        self.assertEqual(result["evidencia"], ["Soy sociable", "prefiero estar solo"])
        self.assertIn("ambos polos", result["explicacion"])

    def test_different_subjects_are_not_one_persons_contradiction(self):
        for text in ("Soy sociable pero ella es reservada", "No soy sociable; ella es sociable",
                     "Ella es reservada; soy sociable"):
            for source in ("comentario", "biografia"):
                with self.subTest(text=text, source=source):
                    self.assert_abstains(text, source)

    def test_reported_or_quoted_speech_is_not_self_reference(self):
        for text in ('Me dijeron que soy sociable', 'Me dijeron: "Soy sociable"',
                     'Ella dice que soy sociable', 'They say I am outgoing',
                     '"Soy sociable"', '\u00abSoy sociable\u00bb', '\u201cSoy sociable\u201d', "'Soy sociable'"):
            for source in ("comentario", "biografia"):
                with self.subTest(text=text, source=source):
                    self.assert_abstains(text, source)

    def test_case_accents_and_whitespace_preserve_original(self):
        text = "¡SOY\t MUY\n EMPÁTICA!"
        result = self.dimension(text, "amabilidad")
        self.assertTrue(result["senal"])
        self.assertEqual(result["evidencia"], ["SOY\t MUY\n EMPÁTICA"])

    def test_decomposed_unicode_preserves_combining_marks(self):
        text = "Soy empA\u0301tica"
        result = self.dimension(text, "amabilidad")
        self.assertEqual(result["evidencia"], [text])

    def test_combining_mark_at_end_of_quote(self):
        text = "Soy sociable\u0301."
        self.assertEqual(self.dimension(text, "extraversion")["evidencia"], ["Soy sociable\u0301"])

    def test_comment_requires_personal_reference(self):
        for text in ("creativa", "sociable", "responsable", "amable", "emocionalmente estable", "La gente sociable es interesante"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_short_bio_is_self_presentation(self):
        result = self.dimension("Soy creativa", "apertura", "biografia")
        self.assertTrue(result["senal"])
        self.assertEqual(result["referencia"], "autopresentacion")
        self.assertEqual(result["evidencia"], ["Soy creativa"])

    def test_single_word_bio_abstains_even_with_nonlinguistic_context(self):
        for text in ("Creativa", "Sociable", "Creativa!", "Sociable, https://example.com/creativa",
                     "https://example.com/soy Sociable", "Sociable, www.creativa.com",
                     "Sociable, #creativa @organizada", "Sociable \U0001f60a\U0001f680", "Sociable 123 _",
                     "Sociable y #creativa", "Outgoing and https://example.com"):
            with self.subTest(text=text):
                self.assert_abstains(text, "biografia")

    def test_bio_list(self):
        text = "Creativa, organizada y sociable"
        results = self.engine.analyze(text, "biografia")
        self.assertEqual([result["dimension"] for result in results if result["senal"]], ["apertura", "responsabilidad", "extraversion"])
        self.assertTrue(all(quote in text for result in results for quote in result["evidencia"]))
        for result in results:
            if result["senal"]:
                self.assertEqual(result["referencia"], "autopresentacion")
                self.assertEqual(result["evidencia"], [text])

    def test_empty_profession_links_hashtags_emojis_bio(self):
        for text in ("", "   ", "Ingeniera", "Psicóloga | Profesora", "https://example.com/sociable", "#sociable #creativa", "\U0001f60a\U0001f680", "www.creativa.com", "@sociable"):
            with self.subTest(text=text):
                self.assert_abstains(text, "biografia")

    def test_negated_bio(self):
        self.assertEqual(self.dimension("No sociable", "extraversion", "biografia")["direccion"], "negativa")

    def test_link_does_not_hide_real_self_presentation(self):
        text = "Soy sociable, https://example.com/creativa"
        results = self.engine.analyze(text, "biografia")
        self.assertFalse(results[0]["senal"])
        self.assertTrue(results[2]["senal"])
        self.assertEqual(results[2]["evidencia"], ["Soy sociable"])

    def test_links_and_tags_do_not_supply_personal_evidence(self):
        for text in ("https://example.com/soy/sociable", "#Soy sociable", "@soy sociable"):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_sarcasm_is_explicitly_limited(self):
        for text in ("Soy sociable /s", "Soy sociable (sarcasmo)", "I am outgoing, yeah right", "Soy sociable \U0001f644"):
            with self.subTest(text=text):
                result = self.dimension(text, "extraversion")
                self.assertTrue(result["senal"])
                self.assertIn("sarcasmo", result["explicacion"])
                self.assertNotIn("%", result["explicacion"])

    def test_malformed_text(self):
        for text in (None, 42, 0.5, True, [], {}, b"Soy sociable", {"text": "Soy sociable"}):
            with self.subTest(text=text):
                self.assert_abstains(text)

    def test_malformed_source(self):
        for source in (None, [], {}, 7, "desconocida"):
            with self.subTest(source=source):
                self.assert_abstains("Soy sociable", source)

    def test_reproducible_and_no_shared_mutation(self):
        text = "Soy creativa y me encanta conocer gente nueva"
        first = self.engine.analyze(text)
        self.assertEqual(first, self.engine.analyze(text))
        first[0]["evidencia"].clear()
        self.assertTrue(self.engine.analyze(text)[0]["evidencia"])

    def test_no_network(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
                patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")), \
                patch.object(socket, "getaddrinfo", side_effect=AssertionError("network forbidden")):
            for text in ("Soy sociable", "https://example.com", "Me preocupo por todo", "Creativa"):
                for source in ("comentario", "biografia"):
                    self.assertEqual(len(self.engine.analyze(text, source)), 5)

    def test_trait_words_are_not_substrings_of_other_words(self):
        self.assert_abstains("Soy sociablemente creativamente")
