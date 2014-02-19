# -*- coding: utf-8 -*-
"""
    user

    Facebook based user authentication code

    :copyright: (c) 2012-2013 by Openlabs Technologies & Consulting (P) LTD
    :license: GPLv3, see LICENSE for more details.
"""
from nereid import url_for, flash, redirect, current_app
from nereid.globals import session, request
from nereid.signals import login, failed_login
from flask_oauth import OAuth
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction

from .i18n import _


__all__ = ['Website', 'NereidUser']
__metaclass__ = PoolMeta


class Website:
    """Add Linkedin settings"""
    __name__ = "nereid.website"

    linkedin_api_key = fields.Char("LinkedIn API Key")
    linkedin_api_secret = fields.Char("LinkedIn Secret Key")

    def get_linkedin_oauth_client(
        self, scope='r_basicprofile,r_emailaddress',
        token='linkedin_oauth_token'
    ):
        """Returns a instance of WebCollect

        :param scope: Scope of information to be fetched from linkedin
        :param token: Token for authentication
        """
        if not all([self.linkedin_api_key, self.linkedin_api_secret]):
            current_app.logger.error("LinkedIn api settings are missing")
            flash(_("LinkedIn login is not available at the moment"))
            return None

        oauth = OAuth()
        linkedin = oauth.remote_app(
            'linkedin',
            base_url='https://api.linkedin.com',
            request_token_url='/uas/oauth/requestToken',
            access_token_url='/uas/oauth/accessToken',
            authorize_url='/uas/oauth/authenticate',
            consumer_key=self.linkedin_api_key,
            consumer_secret=self.linkedin_api_secret,
            request_token_params={'scope': scope}
        )
        linkedin.tokengetter_func = lambda *a: session.get(token)
        return linkedin


class NereidUser:
    "Nereid User"
    __name__ = "nereid.user"

    linkedin_auth = fields.Boolean('LinkedIn Auth')

    @classmethod
    def linkedin_login(cls):
        """The URL to which a new request to authenticate to linedin begins
        Usually issues a redirect.
        """
        linkedin = request.nereid_website.get_linkedin_oauth_client()
        if linkedin is None:
            return redirect(
                request.referrer or url_for('nereid.website.login')
            )
        return linkedin.authorize(
            callback=url_for(
                'nereid.user.linkedin_authorized_login',
                next=request.args.get('next') or request.referrer or None,
                _external=True
            )
        )

    @classmethod
    def linkedin_authorized_login(cls):
        """Authorized handler to which linkedin will redirect the user to
        after the login attempt is made.
        """
        Party = Pool().get('party.party')

        linkedin = request.nereid_website.get_linkedin_oauth_client()
        if linkedin is None:
            return redirect(
                request.referrer or url_for('nereid.website.login')
            )

        try:
            if 'oauth_verifier' in request.args:
                data = linkedin.handle_oauth1_response()
            elif 'code' in request.args:
                data = linkedin.handle_oauth2_response()
            else:
                data = linkedin.handle_unknown_response()
            linkedin.free_request_token()
        except Exception, exc:
            current_app.logger.error("LinkedIn login failed %s" % exc)
            flash(_(
                "We cannot talk to linkedin at this time. Please try again"
            ))
            return redirect(
                request.referrer or url_for('nereid.website.login')
            )

        if data is None:
            flash(_(
                "Access was denied to linkedin: %(reason)s",
                reason=request.args['error_reason']
            ))
            failed_login.send(form=data)
            return redirect(url_for('nereid.website.login'))

        # Write the oauth token to the session
        session['linkedin_oauth_token'] = (
            data['oauth_token'], data['oauth_token_secret']
        )

        # Find the information from facebook
        me = linkedin.get(
            'http://api.linkedin.com/v1/people/~?format=json'
        )
        email = linkedin.get(
            'http://api.linkedin.com/v1/people/~/email-address?format=json'
        )
        session.pop('linkedin_oauth_token')

        # Find the user
        with Transaction().set_context(active_test=False):
            users = cls.search([
                ('email', '=', email.data),
                ('company', '=', request.nereid_website.company.id),
            ])
        if not users:
            current_app.logger.debug(
                "No LinkedIn user with email %s" % email.data
            )
            name = u'%s %s' % (me.data['firstName'], me.data['lastName'])
            current_app.logger.debug("Registering new user %s" % name)
            user, = cls.create([{
                'party': Party.create([{'name': name}])[0].id,
                'display_name': name,
                'email': email.data,
                'linkedin_auth': True,
                'active': True,
            }])
            flash(
                _('Thanks for registering with us using linkedin')
            )
        else:
            user, = users

        # Add the user to session and trigger signals
        session['user'] = user.id
        if not user.linkedin_auth:
            cls.write([user], {'linkedin_auth': True})
        flash(_(
            "You are now logged in. Welcome %(name)s", name=user.rec_name
        ))
        login.send()
        if request.is_xhr:
            return 'OK'
        return redirect(
            request.values.get(
                'next', url_for('nereid.website.home')
            )
        )
