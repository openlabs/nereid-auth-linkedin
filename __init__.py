# -*- coding: utf-8 -*-
"""
    __init__

    LinkedIn based authentication for nereid

    :copyright: (c) 2012-2013 by Openlabs Technologies & Consulting (P) LTD
    :license: GPLv3, see LICENSE for more details.
"""
from trytond.pool import Pool
from .user import Website, NereidUser


def register():
    "Register classes"
    Pool.register(
        Website,
        NereidUser,
        module='nereid_auth_linkedin', type_='model'
    )
