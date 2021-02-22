# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
import pytz

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    @api.model
    def _tz_get(self):
        # put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
        return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

    over_tracking = fields.Float('Over Tracking (%)')
    under_tracking = fields.Float('Under Tracking (%)')
    allow_delayed_check_in = fields.Boolean('Allow Delayed Check In')
    tz = fields.Selection(_tz_get, string='Timezone',
                          help="The Timetracking timezone, used to output proper date and time values for all "
                               "of the timetracking users.")


    @api.model
    def get_values(self):
        response = super(ResConfigSettings, self).get_values()
        Params = self.env['ir.config_parameter']
        over_tracking = Params.get_param('over_tracking', default=0)
        under_tracking = Params.get_param('under_tracking', default=0)
        allow_delayed_check_in = Params.get_param('allow_delayed_check_in', default=False)

        tz = Params.get_param('tz')
        response.update(over_tracking=float(over_tracking))
        response.update(under_tracking=float(under_tracking))
        response.update(allow_delayed_check_in=allow_delayed_check_in)
        response.update(tz=tz)
        return response

    @api.model
    def set_values(self):
        Params = self.env['ir.config_parameter']
        Params.set_param('over_tracking', self.over_tracking)
        Params.set_param('under_tracking', self.under_tracking)
        Params.set_param('allow_delayed_check_in', self.allow_delayed_check_in)
        Params.set_param('tz', self.tz)
        super(ResConfigSettings, self).set_values()
