import os
import shutil

import numpy as np
import tensorflow as tf
import transformers
from absl import app
from absl import flags
from checkpoint_conversion_utils import get_md5_checksum

import keras_hub

PRESET_MAP = {
    "bart_base_en": "facebook/bart-base",
    "bart_large_en": "facebook/bart-large",
    "bart_large_en_cnn": "facebook/bart-large-cnn",
}

FLAGS = flags.FLAGS
flags.DEFINE_string(
    "preset", None, f"Must be one of {','.join(PRESET_MAP.keys())}"
)


def convert_checkpoints(hf_model):
    print("\n-> Convert original weights to KerasHub format.")

    print("\n-> Load KerasHub model.")
    keras_hub_model = keras_hub.models.BartBackbone.from_preset(
        FLAGS.preset, load_weights=False
    )

    hf_wts = hf_model.state_dict()
    print("Original weights:")
    print(list(hf_wts.keys()))

    hidden_dim = keras_hub_model.hidden_dim
    num_heads = keras_hub_model.num_heads

    # Token embedding weights shared by encoder and decoder.
    keras_hub_model.get_layer("token_embedding").embeddings.assign(
        hf_wts["shared.weight"]
    )

    # Encoder weights.
    keras_hub_model.get_layer(
        "encoder_position_embedding"
    ).position_embeddings.assign(hf_wts["encoder.embed_positions.weight"][2:])

    keras_hub_model.get_layer("encoder_embeddings_layer_norm").gamma.assign(
        hf_wts["encoder.layer_norm_embedding.weight"]
    )
    keras_hub_model.get_layer("encoder_embeddings_layer_norm").beta.assign(
        hf_wts["encoder.layer_norm_embedding.bias"]
    )

    for i in range(keras_hub_model.num_layers):
        # Self-attention.
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._query_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.q_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._query_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.q_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._key_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.k_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._key_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.k_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._value_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.v_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._value_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.v_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._output_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.out_proj.weight"]
            .transpose(1, 0)
            .reshape((num_heads, -1, hidden_dim))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer._output_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.self_attn.out_proj.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer_norm.gamma.assign(
            hf_wts[f"encoder.layers.{i}.self_attn_layer_norm.weight"].numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._self_attention_layer_norm.beta.assign(
            hf_wts[f"encoder.layers.{i}.self_attn_layer_norm.bias"].numpy()
        )

        # Post self-attention layers.
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_intermediate_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.fc1.weight"].transpose(1, 0).numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_intermediate_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.fc1.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_output_dense.kernel.assign(
            hf_wts[f"encoder.layers.{i}.fc2.weight"].transpose(1, 0).numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_output_dense.bias.assign(
            hf_wts[f"encoder.layers.{i}.fc2.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_layer_norm.gamma.assign(
            hf_wts[f"encoder.layers.{i}.final_layer_norm.weight"].numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_encoder_layer_{i}"
        )._feedforward_layer_norm.beta.assign(
            hf_wts[f"encoder.layers.{i}.final_layer_norm.bias"].numpy()
        )

    # Decoder weights.

    keras_hub_model.get_layer(
        "decoder_position_embedding"
    ).position_embeddings.assign(hf_wts["decoder.embed_positions.weight"][2:])

    keras_hub_model.get_layer("decoder_embeddings_layer_norm").gamma.assign(
        hf_wts["decoder.layer_norm_embedding.weight"]
    )
    keras_hub_model.get_layer("decoder_embeddings_layer_norm").beta.assign(
        hf_wts["decoder.layer_norm_embedding.bias"]
    )

    for i in range(keras_hub_model.num_layers):
        # Self-attention.
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._query_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.q_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._query_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.q_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._key_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.k_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._key_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.k_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._value_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.v_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._value_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.v_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._output_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.out_proj.weight"]
            .transpose(1, 0)
            .reshape((num_heads, -1, hidden_dim))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer._output_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.self_attn.out_proj.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer_norm.gamma.assign(
            hf_wts[f"decoder.layers.{i}.self_attn_layer_norm.weight"].numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._self_attention_layer_norm.beta.assign(
            hf_wts[f"decoder.layers.{i}.self_attn_layer_norm.bias"].numpy()
        )

        # Cross-attention.
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._query_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.q_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._query_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.q_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._key_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.k_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._key_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.k_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._value_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.v_proj.weight"]
            .transpose(1, 0)
            .reshape((hidden_dim, num_heads, -1))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._value_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.v_proj.bias"]
            .reshape((num_heads, -1))
            .numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._output_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.out_proj.weight"]
            .transpose(1, 0)
            .reshape((num_heads, -1, hidden_dim))
            .numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer._output_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn.out_proj.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer_norm.gamma.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn_layer_norm.weight"].numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._cross_attention_layer_norm.beta.assign(
            hf_wts[f"decoder.layers.{i}.encoder_attn_layer_norm.bias"].numpy()
        )

        # Post self-attention and cross-attention layers.
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_intermediate_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.fc1.weight"].transpose(1, 0).numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_intermediate_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.fc1.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_output_dense.kernel.assign(
            hf_wts[f"decoder.layers.{i}.fc2.weight"].transpose(1, 0).numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_output_dense.bias.assign(
            hf_wts[f"decoder.layers.{i}.fc2.bias"].numpy()
        )

        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_layer_norm.gamma.assign(
            hf_wts[f"decoder.layers.{i}.final_layer_norm.weight"].numpy()
        )
        keras_hub_model.get_layer(
            f"transformer_decoder_layer_{i}"
        )._feedforward_layer_norm.beta.assign(
            hf_wts[f"decoder.layers.{i}.final_layer_norm.bias"].numpy()
        )

    # Save the model.
    print("\n-> Save KerasHub model weights.")
    keras_hub_model.save_weights(os.path.join(FLAGS.preset, "model.h5"))

    return keras_hub_model


def extract_vocab(hf_tokenizer):
    vocabulary_path = os.path.join(FLAGS.preset, "vocab.json")
    merges_path = os.path.join(FLAGS.preset, "merges.txt")
    print(f"\n-> Save KerasHub vocab to `{vocabulary_path}`.")
    print(f"-> Save KerasHub merges to `{merges_path}`.")

    # Huggingface has a save_vocabulary function but it's not byte-for-byte
    # with the source. Instead copy the original downloaded file directly.
    shutil.copyfile(
        transformers.utils.hub.get_file_from_repo(
            hf_tokenizer.name_or_path, "vocab.json"
        ),
        vocabulary_path,
    )
    shutil.copyfile(
        transformers.utils.hub.get_file_from_repo(
            hf_tokenizer.name_or_path, "merges.txt"
        ),
        merges_path,
    )

    keras_hub_tokenizer = keras_hub.models.BartTokenizer(
        vocabulary=vocabulary_path, merges=merges_path
    )

    print("-> Print MD5 checksum of the vocab files.")
    print(f"`{vocabulary_path}` md5sum: ", get_md5_checksum(vocabulary_path))
    print(f"`{merges_path}` md5sum: ", get_md5_checksum(merges_path))

    return keras_hub_tokenizer


def check_output(
    keras_hub_tokenizer,
    keras_hub_model,
    hf_tokenizer,
    hf_model,
):
    print("\n-> Check the outputs.")
    enc_sample_text = [
        "cricket is awesome, easily the best sport in the world!"
    ]
    dec_sample_text = [
        "football is good too, but nowhere near as good as cricket."
    ]

    # KerasHub
    keras_hub_enc_token_ids = keras_hub_tokenizer(
        tf.constant(enc_sample_text)
    ).to_tensor()
    keras_hub_enc_token_ids = tf.concat(
        [
            tf.constant([[keras_hub_tokenizer.start_token_id]]),
            keras_hub_enc_token_ids,
            tf.constant([[keras_hub_tokenizer.end_token_id]]),
        ],
        axis=-1,
    )
    keras_hub_dec_token_ids = keras_hub_tokenizer(
        tf.constant(dec_sample_text)
    ).to_tensor()
    keras_hub_dec_token_ids = tf.concat(
        [
            tf.constant([[keras_hub_tokenizer.start_token_id]]),
            keras_hub_dec_token_ids,
            tf.constant([[keras_hub_tokenizer.end_token_id]]),
        ],
        axis=-1,
    )
    keras_hub_inputs = {
        "encoder_token_ids": keras_hub_enc_token_ids,
        "encoder_padding_mask": keras_hub_enc_token_ids
        != keras_hub_tokenizer.pad_token_id,
        "decoder_token_ids": keras_hub_dec_token_ids,
        "decoder_padding_mask": keras_hub_dec_token_ids
        != keras_hub_tokenizer.pad_token_id,
    }
    keras_hub_output = keras_hub_model.predict(keras_hub_inputs)

    # HF
    hf_enc_inputs = hf_tokenizer(enc_sample_text, return_tensors="pt")
    hf_dec_inputs = hf_tokenizer(dec_sample_text, return_tensors="pt")

    hf_output = hf_model(
        **hf_enc_inputs,
        decoder_input_ids=hf_dec_inputs["input_ids"],
        decoder_attention_mask=hf_dec_inputs["attention_mask"],
    )

    print("Encoder Outputs:")
    print(
        "KerasHub output:",
        keras_hub_output["encoder_sequence_output"][0, 0, :10],
    )
    print("HF output:", hf_output.encoder_last_hidden_state[0, 0, :10])
    print(
        "Difference:",
        np.mean(
            keras_hub_output["encoder_sequence_output"]
            - hf_output.encoder_last_hidden_state.detach().numpy()
        ),
    )

    print("Decoder Outputs:")
    print(
        "KerasHub output:",
        keras_hub_output["decoder_sequence_output"][0, 0, :10],
    )
    print("HF output:", hf_output.last_hidden_state[0, 0, :10])
    print(
        "Difference:",
        np.mean(
            keras_hub_output["decoder_sequence_output"]
            - hf_output.last_hidden_state.detach().numpy()
        ),
    )

    # Show the MD5 checksum of the model weights.
    print(
        "Model md5sum: ",
        get_md5_checksum(os.path.join(FLAGS.preset, "model.h5")),
    )


def main(_):
    os.makedirs(FLAGS.preset)

    hf_model_name = PRESET_MAP[FLAGS.preset]

    print("\n-> Load HF model and HF tokenizer.")
    hf_model = transformers.AutoModel.from_pretrained(hf_model_name)
    hf_model.eval()
    hf_tokenizer = transformers.AutoTokenizer.from_pretrained(hf_model_name)

    keras_hub_model = convert_checkpoints(hf_model)
    print("\n -> Load KerasHub tokenizer.")
    keras_hub_tokenizer = extract_vocab(hf_tokenizer)

    check_output(
        keras_hub_tokenizer,
        keras_hub_model,
        hf_tokenizer,
        hf_model,
    )


if __name__ == "__main__":
    flags.mark_flag_as_required("preset")
    app.run(main)
