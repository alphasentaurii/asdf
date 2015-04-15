# Licensed under a 3-clause BSD style license - see LICENSE.rst
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals, print_function

"""
Utilities for embedded ADSF files in FITS.
"""
import io
import re

import numpy as np

from astropy.extern import six
from astropy.io import fits

from . import asdf
from . import block
from . import util


ASDF_EXTENSION_NAME = 'ASDF'


class _FitsBlock(object):
    def __init__(self, hdu):
        self._hdu = hdu

    def __repr__(self):
        return '<FitsBlock {0},{1}>'.format(self._hdu.name, self._hdu.ver)

    def __len__(self):
        return self._hdu.data.nbytes

    @property
    def data(self):
        return self._hdu.data

    @property
    def array_storage(self):
        return 'fits'


class _EmbeddedBlockManager(block.BlockManager):
    def __init__(self, hdulist, asdffile):
        self._hdulist = hdulist

        super(_EmbeddedBlockManager, self).__init__(asdffile)

    def get_block(self, source):
        if isinstance(source, six.string_types) and source.startswith('fits:'):
            parts = re.match(
                '(?P<name>[A-Z0-9]+)(,(?P<ver>[0-9]+))?', source[5:])
            if parts is not None:
                name = parts.group('name')
                if parts.group('ver'):
                    ver = int(parts.group('ver'))
                    pair = name, ver
                else:
                    pair = name
                return _FitsBlock(self._hdulist[pair])

        return super(_EmbeddedBlockManager, self).get_block(source)

    def get_source(self, block):
        if isinstance(block, _FitsBlock):
            for hdu in self._hdulist:
                if hdu is block._hdu:
                    return 'fits:{0},{1}'.format(hdu.name, hdu.ver)
            raise ValueError("FITS block seems to have been removed")

        return super(_EmbeddedBlockManager, self).get_source(block)

    def find_or_create_block_for_array(self, arr, ctx):
        from .tags.core import ndarray

        if not isinstance(arr, ndarray.NDArrayType):
            base = util.get_array_base(arr)
            for hdu in self._hdulist:
                if base is hdu.data:
                    return _FitsBlock(hdu)

        return super(_EmbeddedBlockManager, self).find_or_create_block_for_array(
            arr, ctx)


class AsdfInFits(asdf.AsdfFile):
    def __init__(self, hdulist=None, tree=None, uri=None, extensions=None):
        if hdulist is None:
            hdulist = fits.HDUList()
        super(AsdfInFits, self).__init__(tree=tree, uri=uri, extensions=extensions)
        self._blocks = _EmbeddedBlockManager(hdulist, self)
        self._hdulist = hdulist

    @classmethod
    def read(cls, hdulist, uri=None, validate_checksums=False, extensions=None):
        try:
            asdf_extension = hdulist[ASDF_EXTENSION_NAME]
        except (KeyError, IndexError, AttributeError):
            return cls(hdulist, uri=uri, extensions=extensions)

        self = cls(hdulist, extensions=extensions)

        buff = io.BytesIO(asdf_extension.data)

        return cls._read_impl(self, buff, uri=uri, mode='r',
                              validate_checksums=validate_checksums)

    def _update_asdf_extension(self, all_array_storage=None,
                               all_array_compression=None,
                               auto_inline=None, pad_blocks=False):
        buff = io.BytesIO()
        super(AsdfInFits, self).write_to(
            buff, all_array_storage=all_array_storage,
            all_array_compression=all_array_compression,
            auto_inline=auto_inline, pad_blocks=pad_blocks)
        array = np.frombuffer(buff.getvalue(), np.uint8)

        try:
            asdf_extension = self._hdulist[ASDF_EXTENSION_NAME]
        except (KeyError, IndexError, AttributeError):
            self._hdulist.append(fits.ImageHDU(array, name=ASDF_EXTENSION_NAME))
        else:
            asdf_extension.data = array

    def write_to(self, filename, all_array_storage=None,
                 all_array_compression=None, auto_inline=None,
                 pad_blocks=False):
        self._update_asdf_extension(
            all_array_storage=all_array_storage,
            all_array_compression=all_array_compression,
            auto_inline=auto_inline, pad_blocks=pad_blocks)

        self._hdulist.writeto(filename)

    def update(self, all_array_storage=None, all_array_compression=None,
               auto_inline=None, pad_blocks=False):
        self._update_asdf_extension(
            all_array_storage=all_array_storage,
            all_array_compression=all_array_compression,
            auto_inline=auto_inline, pad_blocks=pad_blocks)

    def write_to_stream(self, data):
        raise NotImplementedError(
            "Can not stream data to an ASDF file embedded in a FITS file")
