odoo.define('aci_estimation.PivotCustomSearch', (require) => {
    'use strict';

    var rpc = require('web.rpc');
    var PivotModel = require('web.PivotModel');

    PivotModel.include({
        load: function (params) {
            if (this._exist_custom_arguments(params.domain)) {
                var _super = this._super.bind(this);
                return this._retrieve_data_for_custom_arguments(params.domain)
                    .then(() => {
                        return _super(params);
                    });
            } else
                return this._super(params);
        },

        reload: function (handle, params) {
            if (this._exist_custom_arguments(params.domain)) {
                var _super = this._super.bind(this);
                return this._retrieve_data_for_custom_arguments(params.domain)
                    .then(() => {
                        return _super(handle, params);
                    });
            } else
                return this._super(handle, params);
        },

        _exist_custom_arguments: function (domain) {
            var custom_arguments = ['prev_period'];

            for (var idx in custom_arguments)
                if (this._get_index_search_field(domain, custom_arguments[idx]) != -1)
                    return true;
            return false;
        },

        _retrieve_data_for_custom_arguments: function (domain) {
            var self = this;
            return rpc.query({
                    model: 'payment.period.group',
                    method: 'get_general_previous_period'
                }).then((prev_periods) => {
                    return self._review_custom_arguments(domain, prev_periods);
                });
        },

        _review_custom_arguments: function (domain, prev_periods) {
            this._do_replace_custom_argument(domain, 'prev_period', 'period_id', 'in', prev_periods);
        },

        _do_replace_custom_argument: function (domain, field) {
            var new_field = arguments[2] || false,
                new_op = arguments[3] || false,
                new_value = arguments[4] || false;

            var index = this._get_index_search_field(domain, field)
            if (index != -1) {
                if (new_field)
                    domain[index][0] = new_field;
                if (new_op)
                    domain[index][1] = new_op;
                if (new_value)
                    domain[index][2] = new_value;
            }
        },

        _get_index_search_field: function (domain, field) {
            return domain.map(function (item) {return item[0]}).indexOf(field);
        },
    });
});
