import os

import pytest

from keras_hub.src.models.mixtral.mixtral_causal_lm_preprocessor import (
    MixtralCausalLMPreprocessor,
)
from keras_hub.src.models.mixtral.mixtral_tokenizer import MixtralTokenizer
from keras_hub.src.tests.test_case import TestCase


class MixtralCausalLMPreprocessorTest(TestCase):
    def setUp(self):
        self.tokenizer = MixtralTokenizer(
            # Generated using create_mixtral_test_proto.py
            proto=os.path.join(
                self.get_test_data_dir(), "mixtral_test_vocab.spm"
            )
        )
        self.init_kwargs = {
            "tokenizer": self.tokenizer,
            "sequence_length": 8,
        }
        self.input_data = (["the quick brown fox"],)

    def test_preprocessor_basics(self):
        self.run_preprocessor_test(
            cls=MixtralCausalLMPreprocessor,
            init_kwargs=self.init_kwargs,
            input_data=self.input_data,
            expected_output=(
                {
                    "token_ids": [[1, 3, 8, 4, 6, 2, 0, 0]],
                    "padding_mask": [[1, 1, 1, 1, 1, 1, 0, 0]],
                },
                [[3, 8, 4, 6, 2, 0, 0, 0]],  # Pass through labels.
                [[1, 1, 1, 1, 1, 0, 0, 0]],  # Pass through sample_weights.
            ),
        )

    def test_no_start_end_token(self):
        input_data = ["the quick brown fox"] * 4

        preprocessor = MixtralCausalLMPreprocessor(
            **self.init_kwargs,
            add_start_token=False,
            add_end_token=False,
        )
        x, y, sw = preprocessor(input_data)
        self.assertAllEqual(x["token_ids"], [[3, 8, 4, 6, 0, 0, 0, 0]] * 4)
        self.assertAllEqual(x["padding_mask"], [[1, 1, 1, 1, 0, 0, 0, 0]] * 4)
        self.assertAllEqual(y, [[8, 4, 6, 0, 0, 0, 0, 0]] * 4)
        self.assertAllEqual(sw, [[1, 1, 1, 0, 0, 0, 0, 0]] * 4)

    def test_generate_preprocess(self):
        input_data = "the quick brown fox"
        preprocessor = MixtralCausalLMPreprocessor(**self.init_kwargs)
        x = preprocessor.generate_preprocess(input_data)
        self.assertAllEqual(x["token_ids"], [1, 3, 8, 4, 6, 0, 0, 0])
        self.assertAllEqual(x["padding_mask"], [1, 1, 1, 1, 1, 0, 0, 0])

    def test_generate_postprocess(self):
        input_data = {
            "token_ids": [1, 3, 8, 4, 6, 0, 0, 0],
            "padding_mask": [1, 1, 1, 1, 1, 0, 0, 0],
        }
        preprocessor = MixtralCausalLMPreprocessor(**self.init_kwargs)
        x = preprocessor.generate_postprocess(input_data)
        self.assertAllEqual(x, "the quick brown fox")

    @pytest.mark.extra_large
    def test_all_presets(self):
        for preset in MixtralCausalLMPreprocessor.presets:
            self.run_preset_test(
                cls=MixtralCausalLMPreprocessor,
                preset=preset,
                input_data=self.input_data,
            )
