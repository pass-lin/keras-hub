import random

from keras_hub.src.api_export import keras_hub_export
from keras_hub.src.layers.preprocessing.preprocessing_layer import (
    PreprocessingLayer,
)
from keras_hub.src.utils.tensor_utils import convert_to_ragged_batch
from keras_hub.src.utils.tensor_utils import is_int_dtype
from keras_hub.src.utils.tensor_utils import is_string_dtype
from keras_hub.src.utils.tensor_utils import preprocessing_function

try:
    import tensorflow as tf
except ImportError:
    tf = None


@keras_hub_export("keras_hub.layers.RandomSwap")
class RandomSwap(PreprocessingLayer):
    """Augments input by randomly swapping words.

    This layer comes in handy when you need to generate new data using swap
    augmentations as described in the paper [EDA: Easy Data Augmentation
    Techniques for Boosting Performance on Text Classification Tasks]
    (https://arxiv.org/pdf/1901.11196.pdf). The layer expects the inputs to be
    pre-split into token level inputs. This allows control over the level of
    augmentation, you can split by character for character level swaps, or by
    word for word level swaps.

    Input data should be passed as tensors, `tf.RaggedTensor`s, or lists. For
    batched input, inputs should be a list of lists or a rank two tensor. For
    unbatched inputs, each element should be a list or a rank one tensor.

    Args:
        rate: The probability of a given token being chosen to be swapped
            with another random token.
        max_swaps: The maximum number of swaps to be performed.
        skip_list: A list of token values that should not be considered
            candidates for deletion.
        skip_fn: A function that takes as input a scalar tensor token and
            returns as output a scalar tensor True/False value. A value of
            True indicates that the token should not be considered a
            candidate for deletion. This function must be tracable--it
            should consist of tensorflow operations.
        skip_py_fn: A function that takes as input a python token value and
            returns as output `True` or `False`. A value of True
            indicates that should not be considered a candidate for deletion.
            Unlike the `skip_fn` argument, this argument need not be
            tracable--it can be any python function.
        seed: A seed for the random number generator.


    Examples:

    Word level usage.
    >>> keras.utils.set_random_seed(1337)
    >>> x = ["Hey I like", "Keras and Tensorflow"]
    >>> x = list(map(lambda x: x.split(), x))
    >>> augmenter = keras_hub.layers.RandomSwap(rate=0.4, seed=42)
    >>> y = augmenter(x)
    >>> list(map(lambda y: " ".join(y), y))
    ['like I Hey', 'and Keras Tensorflow']

    Character level usage.
    >>> keras.utils.set_random_seed(1337)
    >>> x = ["Hey Dude", "Speed Up"]
    >>> x = list(map(lambda x: list(x), x))
    >>> augmenter = keras_hub.layers.RandomSwap(rate=0.4, seed=42)
    >>> y = augmenter(x)
    >>> list(map(lambda y: "".join(y), y))
    ['deD yuHe', 'SUede pp']

    Usage with skip_list.
    >>> keras.utils.set_random_seed(1337)
    >>> x = ["Hey I like", "Keras and Tensorflow"]
    >>> x = list(map(lambda x: x.split(), x))
    >>> augmenter = keras_hub.layers.RandomSwap(rate=0.4,
    ...     skip_list=["Keras"], seed=42)
    >>> y = augmenter(x)
    >>> list(map(lambda y: " ".join(y), y))
    ['like I Hey', 'Keras and Tensorflow']

    Usage with skip_fn.
    >>> def skip_fn(word):
    ...     return tf.strings.regex_full_match(word, r"[I, a].*")
    >>> keras.utils.set_random_seed(1337)
    >>> x = ["Hey I like", "Keras and Tensorflow"]
    >>> x = list(map(lambda x: x.split(), x))
    >>> augmenter = keras_hub.layers.RandomSwap(rate=0.9, max_swaps=3,
    ...     skip_fn=skip_fn, seed=11)
    >>> y = augmenter(x)
    >>> list(map(lambda y: " ".join(y), y))
    ['like I Hey', 'Keras and Tensorflow']

    Usage with skip_py_fn.
    >>> def skip_py_fn(word):
    ...     return len(word) < 4
    >>> keras.utils.set_random_seed(1337)
    >>> x = ["He was drifting along", "With the wind"]
    >>> x = list(map(lambda x: x.split(), x))
    >>> augmenter = keras_hub.layers.RandomSwap(rate=0.8, max_swaps=2,
    ...     skip_py_fn=skip_py_fn, seed=15)
    >>> y = augmenter(x)
    >>> list(map(lambda y: " ".join(y), y))
    ['He was along drifting', 'wind the With']
    """

    def __init__(
        self,
        rate,
        max_swaps=None,
        skip_list=None,
        skip_fn=None,
        skip_py_fn=None,
        seed=None,
        name=None,
        dtype="int32",
        **kwargs,
    ):
        if not is_int_dtype(dtype) and not is_string_dtype(dtype):
            raise ValueError(
                "Output dtype must be an integer type or a string. "
                f"Received: dtype={dtype}"
            )

        super().__init__(name=name, dtype=dtype, **kwargs)

        self.rate = rate
        self.max_swaps = max_swaps
        self.seed = random.randint(1, int(1e9)) if seed is None else seed
        self._generator = tf.random.Generator.from_seed(self.seed)
        self.skip_list = skip_list
        self.skip_fn = skip_fn
        self.skip_py_fn = skip_py_fn
        if self.max_swaps is not None and self.max_swaps < 0:
            raise ValueError(
                "max_swaps must be non-negative."
                f"Received max_swaps={max_swaps}."
            )

        if [self.skip_list, self.skip_fn, self.skip_py_fn].count(None) < 2:
            raise ValueError(
                "Exactly one of skip_list, skip_fn, skip_py_fn must be "
                "provided."
            )

        if self.skip_list:
            self.StaticHashTable = tf.lookup.StaticHashTable(
                tf.lookup.KeyValueTensorInitializer(
                    tf.convert_to_tensor(self.skip_list),
                    tf.convert_to_tensor([True] * len(self.skip_list)),
                ),
                default_value=False,
            )

    @preprocessing_function
    def call(self, inputs):
        inputs, unbatched, rectangular = convert_to_ragged_batch(inputs)

        skip_masks = None
        if self.skip_list:
            skip_masks = self.StaticHashTable.lookup(inputs.flat_values)
        elif self.skip_fn:
            skip_masks = tf.map_fn(
                self.skip_fn, inputs.flat_values, fn_output_signature="bool"
            )
        elif self.skip_py_fn:

            def string_fn(token):
                return self.skip_py_fn(token.numpy().decode("utf-8"))

            def int_fn(token):
                return self.skip_py_fn(token.numpy())

            py_fn = string_fn if inputs.dtype == tf.string else int_fn

            skip_masks = tf.map_fn(
                lambda x: tf.py_function(py_fn, [x], "bool"),
                inputs.flat_values,
                fn_output_signature="bool",
            )

        positions = tf.ragged.range(inputs.row_lengths())

        if skip_masks is not None:
            skip_masks = tf.logical_not(skip_masks)
            skip_masks.set_shape([None])
            positions = tf.ragged.boolean_mask(
                positions, inputs.with_flat_values(skip_masks)
            )
        # Figure out how many we are going to select.
        token_counts = tf.cast(positions.row_lengths(), "float32")
        num_to_select = tf.random.stateless_binomial(
            shape=tf.shape(token_counts),
            seed=self._generator.make_seeds()[:, 0],
            counts=token_counts,
            probs=self.rate,
        )
        if self.max_swaps is not None:
            num_to_select = tf.math.minimum(num_to_select, self.max_swaps)
        num_to_select = tf.math.minimum(
            num_to_select, tf.cast(positions.row_lengths(), "int32")
        )
        num_to_select = tf.cast(num_to_select, "int64")

        def _swap(x):
            positions, inputs, num_to_select = x
            for _ in range(num_to_select):
                index = tf.random.stateless_uniform(
                    shape=[2],
                    minval=0,
                    maxval=tf.size(positions),
                    dtype="int32",
                    seed=self._generator.make_seeds()[:, 0],
                )
                index1, index2 = positions[index[0]], positions[index[1]]
                # swap items at the sampled indices with each other
                inputs = tf.tensor_scatter_nd_update(
                    inputs,
                    [[index1], [index2]],
                    [inputs[index2], inputs[index1]],
                )
            return inputs

        swapped = tf.map_fn(
            _swap,
            (positions, inputs, num_to_select),
            fn_output_signature=tf.RaggedTensorSpec(
                ragged_rank=positions.ragged_rank - 1, dtype=inputs.dtype
            ),
        )
        swapped.flat_values.set_shape([None])

        if unbatched:
            swapped = tf.squeeze(swapped, axis=0)
        return swapped

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "rate": self.rate,
                "max_swaps": self.max_swaps,
                "seed": self.seed,
                "skip_list": self.skip_list,
                "skip_fn": self.skip_fn,
                "skip_py_fn": self.skip_py_fn,
            }
        )
        return config

    def compute_output_shape(self, inputs_shape):
        inputs_shape = list(inputs_shape)
        inputs_shape[-1] = None
        return tuple(inputs_shape)
