odoo.define('aci_product.many2many_selection', function (require) {
    "use strict";

    var registry = require('web.field_registry');
    var fields = require('web.relational_fields');
    var dialogs = require('web.view_dialogs');
    var core = require('web.core');
    var _t = core._t;

    var FieldMany2One = fields.FieldMany2One.extend({
        template: 'FieldMany2OneSelection',
        events: _.extend({}, fields.FieldMany2One.prototype.events, {
            'click a': '_onInputSelection',
        }),

        _onInputSelection: function () {
            this._searchCreatePopup("search");
        },

        _searchCreatePopup: function (view, ids, context, dynamicFilters) {
            var self = this;
            var context = this.record.getContext(this.recordParams);
            var domain = this.record.getDomain(this.recordParams);
            var blacklisted_ids = this._getSearchBlacklist();
            if (blacklisted_ids.length > 0) {
                domain.push(['id', 'not in', blacklisted_ids]);
            }
            var m2mRecords = [];

            var baseOptions = this._getSearchCreatePopupOptions(view, ids, context, dynamicFilters);
            var options = _.extend({}, baseOptions, {
                domain: domain,
                disable_multiple_selection: false,
                on_selected: function (records) {
                    m2mRecords.push(...records);
                },
                on_closed: function () {
                    self.reinitialize(m2mRecords);
                },
            });
            return new dialogs.SelectCreateDialog(this, options).open();
        }
    });

    var Many2Many_Selection = fields.FieldMany2ManyTags.extend({
        init: function () {
            this._super.apply(this, arguments);
        },

        _renderEdit: function () {
            var self = this;
            if (this.many2one) {
                this.many2one.destroy();
            }
            this.many2one = new FieldMany2One(this, this.name, this.record, {
                mode: 'edit',
                noOpen: true,
                viewType: this.viewType,
                attrs: this.attrs,
            });
            // to prevent the M2O to take the value of the M2M
            this.many2one.value = false;
            // to prevent the M2O to take the relational values of the M2M
            this.many2one.m2o_value = '';

            this.many2one._getSearchBlacklist = function () {
                return self.value.res_ids;
            };

            this.$el.removeClass();
            this.$el.addClass('o_tag_selection');
            return this.many2one.appendTo(this.$el);
        },

    });

    registry.add('many2many_selection', Many2Many_Selection)
    return Many2Many_Selection;

});
