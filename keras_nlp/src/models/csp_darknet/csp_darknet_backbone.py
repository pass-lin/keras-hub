# Copyright 2024 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import keras
from keras import layers

from keras_nlp.src.api_export import keras_nlp_export
from keras_nlp.src.models.backbone import Backbone


@keras_nlp_export("keras_nlp.models.CSPDarkNetBackbone")
class CSPDarkNetBackbone(Backbone):
    """This class represents Keras Backbone of CSPDarkNet model.

    This class implements a CSPDarkNet backbone as described in
    [CSPNet: A New Backbone that can Enhance Learning Capability of CNN](
        https://arxiv.org/abs/1911.11929).

    Args:
        stackwise_num_filters:  A list of ints, filter size for each dark
            level in the model.
        stackwise_depth: A list of ints, the depth for each dark level in the
            model.
        include_rescaling: boolean. If `True`, rescale the input using
            `Rescaling(1 / 255.0)` layer. If `False`, do nothing. Defaults to
            `True`.
        block_type: str. One of `"basic_block"` or `"depthwise_block"`.
            Use `"depthwise_block"` for depthwise conv block
            `"basic_block"` for basic conv block.
            Defaults to "basic_block".
        input_image_shape: tuple. The input shape without the batch size.
            Defaults to `(None, None, 3)`.

    Examples:
    ```python
    input_data = np.ones(shape=(8, 224, 224, 3))

    # Pretrained backbone
    model = keras_nlp.models.CSPDarkNetBackbone.from_preset(
        "csp_darknet_tiny_imagenet"
    )
    model(input_data)

    # Randomly initialized backbone with a custom config
    model = keras_nlp.models.CSPDarkNetBackbone(
        stackwise_num_filters=[128, 256, 512, 1024],
        stackwise_depth=[3, 9, 9, 3],
        include_rescaling=False,
    )
    model(input_data)
    ```
    """

    def __init__(
        self,
        stackwise_num_filters,
        stackwise_depth,
        include_rescaling,
        block_type="basic_block",
        input_image_shape=(224, 224, 3),
        **kwargs,
    ):
        # === Functional Model ===
        apply_ConvBlock = (
            apply_darknet_conv_block_depthwise
            if block_type == "depthwise_block"
            else apply_darknet_conv_block
        )
        base_channels = stackwise_num_filters[0] // 2

        image_input = layers.Input(shape=input_image_shape)
        x = image_input
        if include_rescaling:
            x = layers.Rescaling(scale=1 / 255.0)(x)

        x = apply_focus(name="stem_focus")(x)
        x = apply_darknet_conv_block(
            base_channels, kernel_size=3, strides=1, name="stem_conv"
        )(x)
        for index, (channels, depth) in enumerate(
            zip(stackwise_num_filters, stackwise_depth)
        ):
            x = apply_ConvBlock(
                channels,
                kernel_size=3,
                strides=2,
                name=f"dark{index + 2}_conv",
            )(x)

            if index == len(stackwise_depth) - 1:
                x = apply_spatial_pyramid_pooling_bottleneck(
                    channels,
                    hidden_filters=channels // 2,
                    name=f"dark{index + 2}_spp",
                )(x)

            x = apply_cross_stage_partial(
                channels,
                num_bottlenecks=depth,
                block_type="basic_block",
                residual=(index != len(stackwise_depth) - 1),
                name=f"dark{index + 2}_csp",
            )(x)

        super().__init__(inputs=image_input, outputs=x, **kwargs)

        # === Config ===
        self.stackwise_num_filters = stackwise_num_filters
        self.stackwise_depth = stackwise_depth
        self.include_rescaling = include_rescaling
        self.block_type = block_type
        self.input_image_shape = input_image_shape

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "stackwise_num_filters": self.stackwise_num_filters,
                "stackwise_depth": self.stackwise_depth,
                "include_rescaling": self.include_rescaling,
                "block_type": self.block_type,
                "input_image_shape": self.input_image_shape,
            }
        )
        return config


def apply_focus(name=None):
    """A block used in CSPDarknet to focus information into channels of the
    image.

    If the dimensions of a batch input is (batch_size, width, height, channels),
    this layer converts the image into size (batch_size, width/2, height/2,
    4*channels). See [the original discussion on YoloV5 Focus Layer](https://github.com/ultralytics/yolov5/discussions/3181).

    Args:
        name: the name for the lambda layer used in the block.

    Returns:
        a function that takes an input Tensor representing a Focus layer.
    """

    def apply(x):
        return layers.Concatenate(name=name)(
            [
                x[..., ::2, ::2, :],
                x[..., 1::2, ::2, :],
                x[..., ::2, 1::2, :],
                x[..., 1::2, 1::2, :],
            ],
        )

    return apply


def apply_darknet_conv_block(
    filters, kernel_size, strides, use_bias=False, activation="silu", name=None
):
    """
    The basic conv block used in Darknet. Applies Conv2D followed by a
    BatchNorm.

    Args:
        filters: Integer, the dimensionality of the output space (i.e. the
            number of output filters in the convolution).
        kernel_size: An integer or tuple/list of 2 integers, specifying the
            height and width of the 2D convolution window. Can be a single
            integer to specify the same value both dimensions.
        strides: An integer or tuple/list of 2 integers, specifying the strides
            of the convolution along the height and width. Can be a single
            integer to the same value both dimensions.
        use_bias: Boolean, whether the layer uses a bias vector.
        activation: the activation applied after the BatchNorm layer. One of
            "silu", "relu" or "leaky_relu", defaults to "silu".
        name: the prefix for the layer names used in the block.
    """
    if name is None:
        name = f"conv_block{keras.backend.get_uid('conv_block')}"

    def apply(inputs):
        x = layers.Conv2D(
            filters,
            kernel_size,
            strides,
            padding="same",
            use_bias=use_bias,
            name=name + "_conv",
        )(inputs)

        x = layers.BatchNormalization(name=name + "_bn")(x)

        if activation == "silu":
            x = layers.Lambda(lambda x: keras.activations.silu(x))(x)
        elif activation == "relu":
            x = layers.ReLU()(x)
        elif activation == "leaky_relu":
            x = layers.LeakyReLU(0.1)(x)

        return x

    return apply


def apply_darknet_conv_block_depthwise(
    filters, kernel_size, strides, activation="silu", name=None
):
    """
    The depthwise conv block used in CSPDarknet.

    Args:
        filters: Integer, the dimensionality of the output space (i.e. the
            number of output filters in the final convolution).
        kernel_size: An integer or tuple/list of 2 integers, specifying the
            height and width of the 2D convolution window. Can be a single
            integer to specify the same value both dimensions.
        strides: An integer or tuple/list of 2 integers, specifying the strides
            of the convolution along the height and width. Can be a single
            integer to the same value both dimensions.
        activation: the activation applied after the final layer. One of "silu",
            "relu" or "leaky_relu", defaults to "silu".
        name: the prefix for the layer names used in the block.

    """
    if name is None:
        name = f"conv_block{keras.backend.get_uid('conv_block')}"

    def apply(inputs):
        x = layers.DepthwiseConv2D(
            kernel_size, strides, padding="same", use_bias=False
        )(inputs)
        x = layers.BatchNormalization()(x)

        if activation == "silu":
            x = layers.Lambda(lambda x: keras.activations.swish(x))(x)
        elif activation == "relu":
            x = layers.ReLU()(x)
        elif activation == "leaky_relu":
            x = layers.LeakyReLU(0.1)(x)

        x = apply_darknet_conv_block(
            filters, kernel_size=1, strides=1, activation=activation
        )(x)

        return x

    return apply


def apply_spatial_pyramid_pooling_bottleneck(
    filters,
    hidden_filters=None,
    kernel_sizes=(5, 9, 13),
    activation="silu",
    name=None,
):
    """
    Spatial pyramid pooling layer used in YOLOv3-SPP

    Args:
        filters: Integer, the dimensionality of the output spaces (i.e. the
            number of output filters in used the blocks).
        hidden_filters: Integer, the dimensionality of the intermediate
            bottleneck space (i.e. the number of output filters in the
            bottleneck convolution). If None, it will be equal to filters.
            Defaults to None.
        kernel_sizes: A list or tuple representing all the pool sizes used for
            the pooling layers, defaults to (5, 9, 13).
        activation: Activation for the conv layers, defaults to "silu".
        name: the prefix for the layer names used in the block.

    Returns:
        a function that takes an input Tensor representing an
        SpatialPyramidPoolingBottleneck.
    """
    if name is None:
        name = f"spp{keras.backend.get_uid('spp')}"

    if hidden_filters is None:
        hidden_filters = filters

    def apply(x):
        x = apply_darknet_conv_block(
            hidden_filters,
            kernel_size=1,
            strides=1,
            activation=activation,
            name=f"{name}_conv1",
        )(x)
        x = [x]

        for kernel_size in kernel_sizes:
            x.append(
                layers.MaxPooling2D(
                    kernel_size,
                    strides=1,
                    padding="same",
                    name=f"{name}_maxpool_{kernel_size}",
                )(x[0])
            )

        x = layers.Concatenate(name=f"{name}_concat")(x)
        x = apply_darknet_conv_block(
            filters,
            kernel_size=1,
            strides=1,
            activation=activation,
            name=f"{name}_conv2",
        )(x)

        return x

    return apply


def apply_cross_stage_partial(
    filters,
    num_bottlenecks,
    residual=True,
    block_type="basic_block",
    activation="silu",
    name=None,
):
    """A block used in Cross Stage Partial Darknet.

    Args:
        filters: Integer, the dimensionality of the output space (i.e. the
            number of output filters in the final convolution).
        num_bottlenecks: an integer representing the number of blocks added in
            the layer bottleneck.
        residual: a boolean representing whether the value tensor before the
            bottleneck should be added to the output of the bottleneck as a
            residual, defaults to True.
        block_type: str. One of `"basic_block"` or `"depthwise_block"`.
            Use `"depthwise_block"` for depthwise conv block
            `"basic_block"` for basic conv block.
            Defaults to "basic_block".
        activation: the activation applied after the final layer. One of "silu",
            "relu" or "leaky_relu", defaults to "silu".
    """

    if name is None:
        name = f"cross_stage_partial_{keras.backend.get_uid('cross_stage_partial')}"

    def apply(inputs):
        hidden_channels = filters // 2
        ConvBlock = (
            apply_darknet_conv_block_depthwise
            if block_type == "basic_block"
            else apply_darknet_conv_block
        )

        x1 = apply_darknet_conv_block(
            hidden_channels,
            kernel_size=1,
            strides=1,
            activation=activation,
            name=f"{name}_conv1",
        )(inputs)

        x2 = apply_darknet_conv_block(
            hidden_channels,
            kernel_size=1,
            strides=1,
            activation=activation,
            name=f"{name}_conv2",
        )(inputs)

        for i in range(num_bottlenecks):
            residual_x = x1
            x1 = apply_darknet_conv_block(
                hidden_channels,
                kernel_size=1,
                strides=1,
                activation=activation,
                name=f"{name}_bottleneck_{i}_conv1",
            )(x1)
            x1 = ConvBlock(
                hidden_channels,
                kernel_size=3,
                strides=1,
                activation=activation,
                name=f"{name}_bottleneck_{i}_conv2",
            )(x1)
            if residual:
                x1 = layers.Add(name=f"{name}_bottleneck_{i}_add")(
                    [residual_x, x1]
                )

        x = layers.Concatenate(name=f"{name}_concat")([x1, x2])
        x = apply_darknet_conv_block(
            filters,
            kernel_size=1,
            strides=1,
            activation=activation,
            name=f"{name}_conv3",
        )(x)

        return x

    return apply