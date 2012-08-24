# -*- coding: utf-8 -*-
"""
    user

    Facebook based user authentication code

    :copyright: (c) 2012 by Openlabs Technologies & Consulting (P) LTD
    :license: GPLv3, see LICENSE for more details.
"""
from nereid import url_for, flash, redirect, current_app
from nereid.globals import session, request
from nereid.signals import login, failed_login
from flaskext.oauth import OAuth
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool

from .i18n import _


class Website(ModelSQL, ModelView):
    """Add Linkedin settings"""
    _name = "nereid.website"

    linkedin_api_key = fields.Char("LinkedIn API Key")
    linkedin_api_secret = fields.Char("LinkedIn Secret Key")

    def get_linkedin_oauth_client(self, site=None, 
            scope='r_basicprofile,r_emailaddress',
            token='linkedin_oauth_token'):
        """Returns a instance of WebCollect

        :param site: Browserecord of the website, If not specified, it will be
                     guessed from the request context
        """
        if site is None:
            site = request.nereid_website

        if not all([site.linkedin_api_key, site.linkedin_api_secret]):
            current_app.logger.error("LinkedIn api settings are missing")
            flash(_("LinkedIn login is not available at the moment"))
            return None

        oauth = OAuth()
        linkedin = oauth.remote_app('linkedin',
            base_url='https://api.linkedin.com',
            request_token_url='/uas/oauth/requestToken',
            access_token_url='/uas/oauth/accessToken',
            authorize_url='/uas/oauth/authenticate',
            consumer_key=site.linkedin_api_key,
            consumer_secret=site.linkedin_api_secret,
            request_token_params={'scope': scope}
        )
        linkedin.tokengetter_func = lambda *a: session.get(token)
        return linkedin

Website()


class NereidUser(ModelSQL, ModelView):
    "Nereid User"
    _name = "nereid.user"

    linkedin_auth = fields.Boolean('LinkedIn Auth')

    def linkedin_login(self):
        """The URL to which a new request to authenticate to linedin begins
        Usually issues a redirect.
        """
        website_obj = Pool().get('nereid.website')

        linkedin = website_obj.get_linkedin_oauth_client()
        if linkedin is None:
            return redirect(
                request.referrer or url_for('nereid.website.login')
            )
        return linkedin.authorize(
            callback = url_for('nereid.user.linkedin_authorized_login',
                next = request.args.get('next') or request.referrer or None,
                _external = True
            )
        )

    def linkedin_authorized_login(self):
        """Authorized handler to which linkedin will redirect the user to
        after the login attempt is made.
        """
        website_obj = Pool().get('nereid.website')

        linkedin = website_obj.get_linkedin_oauth_client()
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
            flash(_("We cannot talk to linkedin at this time. Please try again"))
            return redirect(
                request.referrer or url_for('nereid.website.login')
            )

        if data is None:
            flash(
                _("Access was denied to linkedin: %(reason)s",
                reason=request.args['error_reason'])
            )
            failed_login.send(self, form=data)
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
        user_ids = self.search([
            ('email', '=', email.data),
            ('company', '=', request.nereid_website.company.id),
        ])
        if not user_ids:
            current_app.logger.debug(
                "No LinkedIn user with email %s" % email.data
            )
            current_app.logger.debug(
                "Registering new user %s %s" % (
                    me.data['firstName'], me.data['lastName']
                )
            )
            user_id = self.create({
                'name': u'%s %s' % (me.data['firstName'], me.data['lastName']),
                'email': email.data,
                'linkedin_auth': True,
                'addresses': False,
            })
            flash(
                _('Thanks for registering with us using linkedin')
            )
        else:
            user_id, = user_ids

        # Add the user to session and trigger signals
        session['user'] = user_id
        user = self.browse(user_id)
        if not user.linkedin_auth:
            self.write(user_id, {'linkedin_auth': True})
        flash(_("You are now logged in. Welcome %(name)s",
                    name=user.name))
        login.send(self)
        if request.is_xhr:
            return 'OK'
        return redirect(
            request.values.get(
                'next', url_for('nereid.website.home')
            )
        )


NereidUser()
