# -*- coding: utf-8 -*-

from odoo import models, fields, api


class UpdateSequenceWizard(models.TransientModel):
    _name = 'update.sequence.wizard'
    _description = 'Update Sequence Wizard'

    start_sequence = fields.Integer('Start From', default=10)
    increment = fields.Integer('Increment By', default=10)

    def set_sequence(self, record_ids, partition_field=None):
        sequence = self.start_sequence

        for record_id in record_ids.sorted(key=lambda r: r.sequence):
            record_id.sequence = sequence
            sequence += self.increment

    def update_sequence_btn(self):
        self.ensure_one()
        context = self.env.context
        print(context)
        Model = self.env[context.get('source_model') or context.get('active_model')]

        # Get selected records
        selected_ids = Model.browse(context.get('active_ids'))

        if 'partition_by' in context.keys():
            partition_field = context.get('partition_by')
            for partition_id in selected_ids.mapped(partition_field):
                record_ids = selected_ids.filtered(lambda r: r[partition_field] == partition_id)
                self.set_sequence(record_ids, partition_field)
        else:
            self.set_sequence(selected_ids)

    def update_wbs_btn(self):
        self.ensure_one()
        context = self.env.context
        Template = self.env['product.template']

        # Get selected records
        template_ids = Template.browse(context.get('active_ids'))
        for party_id in template_ids.party_id:
            key_t = self.start_sequence
            record_ids = template_ids.filtered(lambda r: r.party_id == party_id)
            for template_id in record_ids.sorted(lambda r: r.sequence):
                key_p = template_id.party_id.sequence // 10000
                template_id.sequence = (key_p * 10000) + (key_t * 100)
                key_t += self.increment

    def update_product_btn(self):
        self.ensure_one()
        context = self.env.context
        Template = self.env['product.template']

        # Get selected records
        for template_id in Template.browse(context.get('active_ids')):
            sequence = template_id.sequence
            for product_id in template_id.product_variant_ids.sorted(key=lambda r: r.sequence):
                product_id.sequence = sequence
                sequence += self.increment
