# -*- coding: utf-8 -*-

# Copyright 2022 Reo Yoneyama (Nagoya University)
#  MIT License (https://opensource.org/licenses/MIT)

"""HiFiGAN and SiFiGAN Generator modules.

References:
    - https://github.com/kan-bayashi/ParallelWaveGAN
    - https://github.com/bigpon/QPPWG
    - https://github.com/jik876/hifi-gan

"""

from logging import getLogger

import torch
import torch.nn as nn
from sifigan.layers import AdaptiveResidualBlock, Conv1d, ResidualBlock

# A logger for this file
logger = getLogger(__name__)


class HiFiGANGenerator(nn.Module):
    """HiFiGAN generator module with customizable pitch-dependent mechanisms."""

    def __init__(
        self,
        in_channels,
        out_channels=1,
        channels=512,
        kernel_size=7,
        upsample_scales=(5, 4, 3, 2),
        upsample_kernel_sizes=(10, 8, 6, 4),
        qp_resblock_kernel_size=3,
        qp_resblock_dilations=[(1,), (1, 2), (1, 2, 4), (1, 2, 4, 8)],
        qp_use_additional_convs=True,
        resblock_kernel_sizes=(3, 7, 11),
        resblock_dilations=[(1, 3, 5), (1, 3, 5), (1, 3, 5)],
        use_additional_convs=False,
        use_sine_embs=False,
        use_qp_resblocks=False,
        bias=True,
        nonlinear_activation="LeakyReLU",
        nonlinear_activation_params={"negative_slope": 0.1},
        use_weight_norm=True,
    ):
        """Initialize QpHiFiGANGenerator module.

        Args:
            in_channels (int): Number of input channels.
            out_channels (int): Number of output channels.
            channels (int): Number of hidden representation channels.
            kernel_size (int): Kernel size of initial and final conv layer.
            upsample_scales (list): List of upsampling scales.
            upsample_kernel_sizes (list): List of kernel sizes for upsampling layers.
            qp_resblock_kernel_size (int): Kernel size for quasi-periodic residual blocks.
            qp_resblock_dilations (list): Dilations for quasi-periodic residual blocks.
            qp_use_additional_convs (bool): Whether to use additional conv layers.
            resblock_kernel_sizes (list): List of kernel sizes for residual blocks.
            resblock_dilations (list): List of dilation list for residual blocks.
            use_additional_convs (bool): Whether to use additional conv layers in residual blocks.
            use_sine_embs (bool): Whether to use sine embeddings.
            use_qp_resblocks (bool): Whether to use quasi-periodic residual blocks.
            bias (bool): Whether to add bias parameter in convolution layers.
            nonlinear_activation (str): Activation function module name.
            nonlinear_activation_params (dict): Hyperparameters for activation function.
            use_weight_norm (bool): Whether to use weight norm.
                If set to true, it will be applied to all of the conv layers.

        """
        super().__init__()
        # check hyperparameters are valid
        assert kernel_size % 2 == 1, "Kernel size must be odd number."
        assert len(upsample_scales) == len(upsample_kernel_sizes)
        assert len(resblock_dilations) == len(resblock_kernel_sizes)

        # define modules
        self.num_upsamples = len(upsample_kernel_sizes)
        self.qp_resdual_dilations = qp_resblock_dilations
        self.num_blocks = len(resblock_kernel_sizes)
        self.input_conv = Conv1d(
            in_channels,
            channels,
            kernel_size,
            bias=bias,
            padding=(kernel_size - 1) // 2,
        )
        self.upsamples = nn.ModuleList()
        self.use_qp_resblocks = use_qp_resblocks
        if use_qp_resblocks:
            self.qp_blocks = nn.ModuleList()
        self.blocks = nn.ModuleList()
        for i in range(len(upsample_kernel_sizes)):
            assert upsample_kernel_sizes[i] == 2 * upsample_scales[i]
            self.upsamples += [
                nn.Sequential(
                    getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                    nn.ConvTranspose1d(
                        channels // (2 ** i),
                        channels // (2 ** (i + 1)),
                        upsample_kernel_sizes[i],
                        upsample_scales[i],
                        padding=upsample_scales[i] // 2 + upsample_scales[i] % 2,
                        output_padding=upsample_scales[i] % 2,
                        bias=bias,
                    ),
                )
            ]
            if use_qp_resblocks:
                self.qp_blocks += [
                    AdaptiveResidualBlock(
                        kernel_size=qp_resblock_kernel_size,
                        channels=channels // (2 ** (i + 1)),
                        dilations=qp_resblock_dilations[i],
                        bias=bias,
                        use_additional_convs=qp_use_additional_convs,
                        nonlinear_activation=nonlinear_activation,
                        nonlinear_activation_params=nonlinear_activation_params,
                    )
                ]
            for j in range(len(resblock_kernel_sizes)):
                self.blocks += [
                    ResidualBlock(
                        kernel_size=resblock_kernel_sizes[j],
                        channels=channels // (2 ** (i + 1)),
                        dilations=resblock_dilations[j],
                        bias=bias,
                        use_additional_convs=use_additional_convs,
                        nonlinear_activation=nonlinear_activation,
                        nonlinear_activation_params=nonlinear_activation_params,
                    )
                ]
        self.output_conv = nn.Sequential(
            nn.LeakyReLU(),
            nn.Conv1d(
                channels // (2 ** (i + 1)),
                out_channels,
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            ),
            nn.Tanh(),
        )

        # sine embedding layers
        self.use_sine_embs = use_sine_embs
        if use_sine_embs:
            self.emb = Conv1d(
                1,
                channels // (2 ** len(upsample_kernel_sizes)),
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            )
            self.downsamples = nn.ModuleList()
            for i in reversed(range(len(upsample_kernel_sizes))):
                self.downsamples += [
                    nn.Sequential(
                        nn.Conv1d(
                            channels // (2 ** (i + 1)),
                            channels // (2 ** i),
                            upsample_kernel_sizes[i],
                            upsample_scales[i],
                            padding=upsample_scales[i] - (upsample_kernel_sizes[i] % 2 == 0),
                            bias=bias,
                        ),
                        getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                    )
                ]

        # apply weight norm
        if use_weight_norm:
            self.apply_weight_norm()

        # reset parameters
        self.reset_parameters()

    def forward(self, x, c, d=None):
        """Calculate forward propagation.

        Args:
            x (Tensor): Input sine signal (B, 1, T).
            c (Tensor): Input tensor (B, in_channels, T).
            d (List): F0-dependent dilation factors [(B, 1, T) x num_upsamples].

        Returns:
            Tensor: Output tensor (B, out_channels, T).

        """
        c = self.input_conv(c)

        if self.use_sine_embs:
            x = self.emb(x)
            embs = [x]
            for i in range(self.num_upsamples - 1):
                x = self.downsamples[i](x)
                embs += [x]

        for i in range(self.num_upsamples):
            c = self.upsamples[i](c)
            if self.use_sine_embs:
                c = c + embs[-i - 1]
            if self.use_qp_resblocks:
                c = self.qp_blocks[i](c, d[i])
            cs = 0.0  # initialize
            for j in range(self.num_blocks):
                cs += self.blocks[i * self.num_blocks + j](c)
            c = cs / self.num_blocks
        c = self.output_conv(c)

        return (c,)

    def reset_parameters(self):
        """Reset parameters.

        This initialization follows the official implementation manner.
        https://github.com/jik876/hifi-gan/blob/master/models.py

        """

        def _reset_parameters(m):
            if isinstance(m, (nn.Conv1d, nn.ConvTranspose1d)):
                m.weight.data.normal_(0.0, 0.01)
                logger.debug(f"Reset parameters in {m}.")

        self.apply(_reset_parameters)

    def remove_weight_norm(self):
        """Remove weight normalization module from all of the layers."""

        def _remove_weight_norm(m):
            try:
                logger.debug(f"Weight norm is removed from {m}.")
                nn.utils.remove_weight_norm(m)
            except ValueError:  # this module didn't have weight norm
                return

        self.apply(_remove_weight_norm)

    def apply_weight_norm(self):
        """Apply weight normalization module from all of the layers."""

        def _apply_weight_norm(m):
            if isinstance(m, nn.Conv1d) or isinstance(m, nn.ConvTranspose1d):
                nn.utils.weight_norm(m)
                logger.debug(f"Weight norm is applied to {m}.")

        self.apply(_apply_weight_norm)


class SiFiGANGenerator(nn.Module):
    """SiFiGAN generator module."""

    def __init__(
        self,
        in_channels,
        out_channels=1,
        channels=512,
        kernel_size=7,
        upsample_scales=(5, 4, 3, 2),
        upsample_kernel_sizes=(10, 8, 6, 4),
        source_network_params={
            "resblock_kernel_size": 3,  # currently only 3 is supported.
            "resblock_dilations": [(1,), (1, 2), (1, 2, 4), (1, 2, 4, 8)],
            "use_additional_convs": True,
        },
        filter_network_params={
            "resblock_kernel_sizes": (3, 5, 7),
            "resblock_dilations": [(1, 3, 5), (1, 3, 5), (1, 3, 5)],
            "use_additional_convs": False,
        },
        share_upsamples=False,
        share_downsamples=False,
        bias=True,
        nonlinear_activation="LeakyReLU",
        nonlinear_activation_params={"negative_slope": 0.1},
        use_weight_norm=True,
        gin_channels = 256,
    ):
        """Initialize SiFiGANGenerator module.

        Args:
            in_channels (int): Number of input channels.
            out_channels (int): Number of output channels.
            channels (int): Number of hidden representation channels.
            kernel_size (int): Kernel size of initial and final conv layer.
            upsample_scales (list): List of upsampling scales.
            upsample_kernel_sizes (list): List of kernel sizes for upsampling layers.
            source_network_params (dict): Parameters for source-network.
            filter_network_params (dict): Parameters for filter-network.
            share_upsamples (bool): Whether to share up-sampling transposed CNNs.
            share_downsamples (bool): Whether to share down-sampling CNNs.
            bias (bool): Whether to add bias parameter in convolution layers.
            nonlinear_activation (str): Activation function module name.
            nonlinear_activation_params (dict): Hyperparameters for activation function.
            use_weight_norm (bool): Whether to use weight norm.
                If set to true, it will be applied to all of the conv layers.

        """
        super().__init__()
        # check hyperparameters are valid
        assert kernel_size % 2 == 1, "Kernel size must be odd number."
        assert len(upsample_scales) == len(upsample_kernel_sizes)

        #emb sid
        if gin_channels != 0:
            self.emb_g = nn.Embedding(12, gin_channels)
            self.cond = nn.Conv1d(gin_channels, channels, 1)

        # define modules
        self.num_upsamples = len(upsample_kernel_sizes)
        self.source_network_params = source_network_params
        self.filter_network_params = filter_network_params
        self.share_upsamples = share_upsamples
        self.share_downsamples = share_downsamples
        self.sn = nn.ModuleDict()
        self.fn = nn.ModuleDict()
        self.input_conv = Conv1d(
            in_channels,
            channels,
            kernel_size,
            bias=bias,
            padding=(kernel_size - 1) // 2,
        )
        self.sn["upsamples"] = nn.ModuleList()
        self.fn["upsamples"] = nn.ModuleList()
        self.sn["blocks"] = nn.ModuleList()
        self.fn["blocks"] = nn.ModuleList()
        for i in range(len(upsample_kernel_sizes)):
            assert upsample_kernel_sizes[i] == 2 * upsample_scales[i]
            self.sn["upsamples"] += [
                nn.Sequential(
                    getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                    nn.ConvTranspose1d(
                        channels // (2 ** i),
                        channels // (2 ** (i + 1)),
                        upsample_kernel_sizes[i],
                        upsample_scales[i],
                        padding=upsample_scales[i] // 2 + upsample_scales[i] % 2,
                        output_padding=upsample_scales[i] % 2,
                        bias=bias,
                    ),
                )
            ]
            if not share_upsamples:
                self.fn["upsamples"] += [
                    nn.Sequential(
                        getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                        nn.ConvTranspose1d(
                            channels // (2 ** i),
                            channels // (2 ** (i + 1)),
                            upsample_kernel_sizes[i],
                            upsample_scales[i],
                            padding=upsample_scales[i] // 2 + upsample_scales[i] % 2,
                            output_padding=upsample_scales[i] % 2,
                            bias=bias,
                        ),
                    )
                ]
            self.sn["blocks"] += [
                AdaptiveResidualBlock(
                    kernel_size=source_network_params["resblock_kernel_size"],
                    channels=channels // (2 ** (i + 1)),
                    dilations=source_network_params["resblock_dilations"][i],
                    bias=bias,
                    use_additional_convs=source_network_params["use_additional_convs"],
                    nonlinear_activation=nonlinear_activation,
                    nonlinear_activation_params=nonlinear_activation_params,
                )
            ]
            for j in range(len(filter_network_params["resblock_kernel_sizes"])):
                self.fn["blocks"] += [
                    ResidualBlock(
                        kernel_size=filter_network_params["resblock_kernel_sizes"][j],
                        channels=channels // (2 ** (i + 1)),
                        dilations=filter_network_params["resblock_dilations"][j],
                        bias=bias,
                        use_additional_convs=filter_network_params["use_additional_convs"],
                        nonlinear_activation=nonlinear_activation,
                        nonlinear_activation_params=nonlinear_activation_params,
                    )
                ]
        self.sn["output_conv"] = nn.Sequential(
            nn.LeakyReLU(),
            nn.Conv1d(
                channels // (2 ** (i + 1)),
                out_channels,
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            ),
        )
        self.fn["output_conv"] = nn.Sequential(
            nn.LeakyReLU(),
            nn.Conv1d(
                channels // (2 ** (i + 1)),
                out_channels,
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            ),
            nn.Tanh(),
        )

        # sine embedding layers
        self.sn["emb"] = Conv1d(
            1,
            channels // (2 ** len(upsample_kernel_sizes)),
            kernel_size,
            bias=bias,
            padding=(kernel_size - 1) // 2,
        )
        # down-sampling CNNs
        self.sn["downsamples"] = nn.ModuleList()
        for i in reversed(range(len(upsample_kernel_sizes))):
            self.sn["downsamples"] += [
                nn.Sequential(
                    nn.Conv1d(
                        channels // (2 ** (i + 1)),
                        channels // (2 ** i),
                        upsample_kernel_sizes[i],
                        upsample_scales[i],
                        padding=upsample_scales[i] - (upsample_kernel_sizes[i] % 2 == 0),
                        bias=bias,
                    ),
                    getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                )
            ]
        if not share_downsamples:
            self.fn["downsamples"] = nn.ModuleList()
            for i in reversed(range(len(upsample_kernel_sizes))):
                self.fn["downsamples"] += [
                    nn.Sequential(
                        nn.Conv1d(
                            channels // (2 ** (i + 1)),
                            channels // (2 ** i),
                            upsample_kernel_sizes[i],
                            upsample_scales[i],
                            padding=upsample_scales[i] - (upsample_kernel_sizes[i] % 2 == 0),
                            bias=bias,
                        ),
                        getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                    )
                ]

        # apply weight norm
        if use_weight_norm:
            self.apply_weight_norm()

        # reset parameters
        self.reset_parameters()

    def forward(self, x, c, d, sid):
        """Calculate forward propagation.

        Args:
            x (Tensor): Input sine signal (B, 1, T).
            c (Tensor): Input tensor (B, in_channels, T).
            d (List): F0-dependent dilation factors [(B, 1, T) x num_upsamples].

        Returns:
            Tensor: Output tensor (B, out_channels, T).

        """

        #sid
        sid_ = self.emb_g(sid).unsqueeze(-1)
        sid_ = self.cond(sid_)
        # currently, same input feature is input to each network
        c = self.input_conv(c) + sid_
        e = c

        # source-network forward
        x = self.sn["emb"](x)
        embs = [x]
        for i in range(self.num_upsamples - 1):
            x = self.sn["downsamples"][i](x)
            embs += [x]
        for i in range(self.num_upsamples):
            # excitation generation network
            e = self.sn["upsamples"][i](e) + embs[-i - 1]
            e = self.sn["blocks"][i](e, d[i])
        e_ = self.sn["output_conv"](e)

        # filter-network forward
        embs = [e]
        for i in range(self.num_upsamples - 1):
            if self.share_downsamples:
                e = self.sn["downsamples"][i](e)
            else:
                e = self.fn["downsamples"][i](e)
            embs += [e]
        num_blocks = len(self.filter_network_params["resblock_kernel_sizes"])
        for i in range(self.num_upsamples):
            # resonance filtering network
            if self.share_upsamples:
                c = self.sn["upsamples"][i](c) + embs[-i - 1]
            else:
                c = self.fn["upsamples"][i](c) + embs[-i - 1]
            cs = 0.0  # initialize
            for j in range(num_blocks):
                cs += self.fn["blocks"][i * num_blocks + j](c)
            c = cs / num_blocks
        c = self.fn["output_conv"](c)

        return c, e_

    def reset_parameters(self):
        """Reset parameters.

        This initialization follows the official implementation manner.
        https://github.com/jik876/hifi-gan/blob/master/models.py

        """

        def _reset_parameters(m):
            if isinstance(m, (nn.Conv1d, nn.ConvTranspose1d)):
                m.weight.data.normal_(0.0, 0.01)
                logger.debug(f"Reset parameters in {m}.")

        self.apply(_reset_parameters)

    def remove_weight_norm(self):
        """Remove weight normalization module from all of the layers."""

        def _remove_weight_norm(m):
            try:
                logger.debug(f"Weight norm is removed from {m}.")
                nn.utils.remove_weight_norm(m)
            except ValueError:  # this module didn't have weight norm
                return

        self.apply(_remove_weight_norm)

    def apply_weight_norm(self):
        """Apply weight normalization module from all of the layers."""

        def _apply_weight_norm(m):
            if isinstance(m, nn.Conv1d) or isinstance(m, nn.ConvTranspose1d):
                nn.utils.weight_norm(m)
                logger.debug(f"Weight norm is applied to {m}.")

        self.apply(_apply_weight_norm)


class SiFiGANDirectGenerator(nn.Module):
    """SiFiGAN Direct generator module."""

    def __init__(
        self,
        in_channels,
        out_channels=1,
        channels=512,
        kernel_size=7,
        upsample_scales=(5, 4, 3, 2),
        upsample_kernel_sizes=(10, 8, 6, 4),
        source_network_params={
            "resblock_kernel_size": 3,  # currently only 3 is supported.
            "resblock_dilations": [(1,), (1, 2), (1, 2, 4), (1, 2, 4, 8)],
            "use_additional_convs": True,
        },
        filter_network_params={
            "resblock_kernel_sizes": (3, 5, 7),
            "resblock_dilations": [(1, 3, 5), (1, 3, 5), (1, 3, 5)],
            "use_additional_convs": False,
        },
        share_upsamples=False,
        bias=True,
        nonlinear_activation="LeakyReLU",
        nonlinear_activation_params={"negative_slope": 0.1},
        use_weight_norm=True,
    ):
        """Initialize SiFiGANDirectGenerator module.

        Args:
            in_channels (int): Number of input channels.
            out_channels (int): Number of output channels.
            channels (int): Number of hidden representation channels.
            kernel_size (int): Kernel size of initial and final conv layer.
            upsample_scales (list): List of upsampling scales.
            upsample_kernel_sizes (list): List of kernel sizes for upsampling layers.
            source_network_params (dict): Parameters for source-network.
            filter_network_params (dict): Parameters for filter-network.
            share_upsamples (bool): Whether to share up-sampling transposed CNNs.
            share_downsamples (bool): Whether to share down-sampling CNNs.
            bias (bool): Whether to add bias parameter in convolution layers.
            nonlinear_activation (str): Activation function module name.
            nonlinear_activation_params (dict): Hyperparameters for activation function.
            use_weight_norm (bool): Whether to use weight norm.
                If set to true, it will be applied to all of the conv layers.

        """
        super().__init__()
        # check hyperparameters are valid
        assert kernel_size % 2 == 1, "Kernel size must be odd number."
        assert len(upsample_scales) == len(upsample_kernel_sizes)

        # define modules
        self.num_upsamples = len(upsample_kernel_sizes)
        self.source_network_params = source_network_params
        self.filter_network_params = filter_network_params
        self.share_upsamples = share_upsamples
        self.sn = nn.ModuleDict()
        self.fn = nn.ModuleDict()
        self.input_conv = Conv1d(
            in_channels,
            channels,
            kernel_size,
            bias=bias,
            padding=(kernel_size - 1) // 2,
        )
        self.sn["upsamples"] = nn.ModuleList()
        self.fn["upsamples"] = nn.ModuleList()
        self.sn["blocks"] = nn.ModuleList()
        self.fn["blocks"] = nn.ModuleList()
        for i in range(len(upsample_kernel_sizes)):
            assert upsample_kernel_sizes[i] == 2 * upsample_scales[i]
            self.sn["upsamples"] += [
                nn.Sequential(
                    getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                    nn.ConvTranspose1d(
                        channels // (2 ** i),
                        channels // (2 ** (i + 1)),
                        upsample_kernel_sizes[i],
                        upsample_scales[i],
                        padding=upsample_scales[i] // 2 + upsample_scales[i] % 2,
                        output_padding=upsample_scales[i] % 2,
                        bias=bias,
                    ),
                )
            ]
            if not share_upsamples:
                self.fn["upsamples"] += [
                    nn.Sequential(
                        getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                        nn.ConvTranspose1d(
                            channels // (2 ** i),
                            channels // (2 ** (i + 1)),
                            upsample_kernel_sizes[i],
                            upsample_scales[i],
                            padding=upsample_scales[i] // 2 + upsample_scales[i] % 2,
                            output_padding=upsample_scales[i] % 2,
                            bias=bias,
                        ),
                    )
                ]
            self.sn["blocks"] += [
                AdaptiveResidualBlock(
                    kernel_size=source_network_params["resblock_kernel_size"],
                    channels=channels // (2 ** (i + 1)),
                    dilations=source_network_params["resblock_dilations"][i],
                    bias=bias,
                    use_additional_convs=source_network_params["use_additional_convs"],
                    nonlinear_activation=nonlinear_activation,
                    nonlinear_activation_params=nonlinear_activation_params,
                )
            ]
            for j in range(len(filter_network_params["resblock_kernel_sizes"])):
                self.fn["blocks"] += [
                    ResidualBlock(
                        kernel_size=filter_network_params["resblock_kernel_sizes"][j],
                        channels=channels // (2 ** (i + 1)),
                        dilations=filter_network_params["resblock_dilations"][j],
                        bias=bias,
                        use_additional_convs=filter_network_params["use_additional_convs"],
                        nonlinear_activation=nonlinear_activation,
                        nonlinear_activation_params=nonlinear_activation_params,
                    )
                ]
        self.sn["output_conv"] = nn.Sequential(
            nn.LeakyReLU(),
            nn.Conv1d(
                channels // (2 ** (i + 1)),
                out_channels,
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            ),
        )
        self.fn["output_conv"] = nn.Sequential(
            nn.LeakyReLU(),
            nn.Conv1d(
                channels // (2 ** (i + 1)),
                out_channels,
                kernel_size,
                bias=bias,
                padding=(kernel_size - 1) // 2,
            ),
            nn.Tanh(),
        )

        # sine embedding layers
        self.sn["emb"] = Conv1d(
            1,
            channels // (2 ** len(upsample_kernel_sizes)),
            kernel_size,
            bias=bias,
            padding=(kernel_size - 1) // 2,
        )
        # down-sampling CNNs
        self.sn["downsamples"] = nn.ModuleList()
        for i in reversed(range(len(upsample_kernel_sizes))):
            self.sn["downsamples"] += [
                nn.Sequential(
                    nn.Conv1d(
                        channels // (2 ** (i + 1)),
                        channels // (2 ** i),
                        upsample_kernel_sizes[i],
                        upsample_scales[i],
                        padding=upsample_scales[i] - (upsample_kernel_sizes[i] % 2 == 0),
                        bias=bias,
                    ),
                    getattr(nn, nonlinear_activation)(**nonlinear_activation_params),
                )
            ]

        # apply weight norm
        if use_weight_norm:
            self.apply_weight_norm()

        # reset parameters
        self.reset_parameters()

    def forward(self, x, c, d):
        """Calculate forward propagation.

        Args:
            x (Tensor): Input sine signal (B, 1, T).
            c (Tensor): Input tensor (B, in_channels, T).
            d (List): F0-dependent dilation factors [(B, 1, T) x num_upsamples].

        Returns:
            Tensor: Output tensor (B, out_channels, T).

        """
        # currently, same input feature is input to each network
        c = self.input_conv(c)
        e = c

        # source-network forward
        x = self.sn["emb"](x)
        embs = [x]
        for i in range(self.num_upsamples - 1):
            x = self.sn["downsamples"][i](x)
            embs += [x]
        embs2 = []
        for i in range(self.num_upsamples):
            # excitation generation network
            e = self.sn["upsamples"][i](e) + embs[-i - 1]
            e = self.sn["blocks"][i](e, d[i])
            embs2 += [e]
        e = self.sn["output_conv"](e)

        # filter-network forward
        num_blocks = len(self.filter_network_params["resblock_kernel_sizes"])
        for i in range(self.num_upsamples):
            # resonance filtering network
            if self.share_upsamples:
                c = self.sn["upsamples"][i](c) + embs2[i]
            else:
                c = self.fn["upsamples"][i](c) + embs2[i]
            cs = 0.0  # initialize
            for j in range(num_blocks):
                cs += self.fn["blocks"][i * num_blocks + j](c)
            c = cs / num_blocks
        c = self.fn["output_conv"](c)

        return c, e

    def reset_parameters(self):
        """Reset parameters.

        This initialization follows the official implementation manner.
        https://github.com/jik876/hifi-gan/blob/master/models.py

        """

        def _reset_parameters(m):
            if isinstance(m, (nn.Conv1d, nn.ConvTranspose1d)):
                m.weight.data.normal_(0.0, 0.01)
                logger.debug(f"Reset parameters in {m}.")

        self.apply(_reset_parameters)

    def remove_weight_norm(self):
        """Remove weight normalization module from all of the layers."""

        def _remove_weight_norm(m):
            try:
                logger.debug(f"Weight norm is removed from {m}.")
                nn.utils.remove_weight_norm(m)
            except ValueError:  # this module didn't have weight norm
                return

        self.apply(_remove_weight_norm)

    def apply_weight_norm(self):
        """Apply weight normalization module from all of the layers."""

        def _apply_weight_norm(m):
            if isinstance(m, nn.Conv1d) or isinstance(m, nn.ConvTranspose1d):
                nn.utils.weight_norm(m)
                logger.debug(f"Weight norm is applied to {m}.")

        self.apply(_apply_weight_norm)
