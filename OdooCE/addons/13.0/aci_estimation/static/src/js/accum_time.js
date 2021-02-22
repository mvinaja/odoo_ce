odoo.define('aci_estimation.AccumTime_Controler', function (require) {
    'use strict';

    var core = require('web.core');
    var Formview = require('web.FormView');
    var basic_fields = require('web.basic_fields');
    var field_registry = require('web.field_registry');
    var Widget = require('web.Widget');
    var AbstractField = require('web.AbstractField');
    var time = require('web.time');
    var rpc = require('web.rpc');
    var FormController = require('web.FormController');
    var config = require('web.config');
    var ViewsWidget = require('stock_barcode.ViewsWidget');
//    var moment = require('moment');

    var qweb = core.qweb;

    var accum_times = AbstractField.extend({
        init: function (parent, model, renderer, params) {
            this._super(parent, model, renderer, params)
        },
        _render: function () {

        },
         willStart: function () {
            return $.when(this._super.apply(this, arguments));
        },

    });

    var accum_times = AbstractField.extend({
    init: function (parent, model, renderer, params) {
        this._super(parent, model, renderer, params);
    },

    _render: function () {
        this._startTimeCounter();
    },
     _getDateDifference: function (dateStart, dateEnd) {
        return moment(dateEnd).diff(moment(dateStart));
    },
    willStart: function () {
        var self = this;
        var def = this._rpc({
             model: 'ir.config_parameter',
             method: 'get_param',
             args: ['tracking_timer'],
        }).then(function (result) {
            if (result){
                self.duration = parseInt(result)*1000;
            }
            else{ self.duration = 20000}
        });
        return $.when(this._super.apply(this, arguments), def);
    },

    _startTimeCounter: function () {
        var self = this;
        clearTimeout(this.timer)
        if (self.duration > 0){
           this.timer = setTimeout(function () {
            self.duration -= 1000;
            self._startTimeCounter();
            }, 1000);
            this.$el.html($('<span>' + moment.utc(self.duration).format("HH:mm:ss") + '</span>'));
           }
            else {
            self.duration = 0
            this.$el.html($('<span>' + moment.utc(self.duration).format("HH:mm:ss") + '</span>'));
            clearTimeout(this.timer);
            this.set_close_record();
        }
      },
      destroy: function () {
        this._super.apply(this, arguments);
        clearTimeout(this.timer);
       },

      set_close_record (){
        this.do_action({type: 'ir.actions.act_window_close'});
        },
    });

    var accum_productivity = AbstractField.extend({
        init: function (parent, model, renderer, params) {
            this._super.apply(this, arguments);
//             this.mode = 'edit'
        },

        _render: function () {
            this._startTimeCounter();
        },
         _getDateDifference: function (dateStart, dateEnd) {
            return moment(dateEnd).diff(moment(dateStart));
        },
        willStart: function () {
            var self = this;
//            self.mode = false
            self.record_ids = []
            var get_productivity;
            var currentDate = new Date();
            var view = this.recordData.activity_ids.viewType = 'tree';
            var def = rpc.query({
                model: 'time.tracking.actions.wizard',
                method: 'get_time_block',
                args: [this.res_id, this.recordData.key]
            }).then(function (duration) {
                        self.accum_time = moment(duration)
                        self.block_step = true
                   });
            return $.when(this._super.apply(this, arguments), def,view);
        },

        _getDateDifference: function (dateStart, dateEnd) {
                return moment(dateEnd).diff(moment(dateStart));
        },

        isSet: function () {
            return true;
        },


        _startTimeCounter: function () {
            var self = this;
            clearTimeout(this.timer_by_step)
            if (self.block_step == true){
                this.timer_by_step = setTimeout(function () {
                    self.duration_by_step += 1000;
                    self.accum_time += 1000;
                    self._startTimeCounter();
                    }, 1000);
                this.$el.html($('<span>' + moment.utc(self.accum_time).format("HH:mm:ss") + '</span>'));
            }
        },

        destroy: function () {
            this._super.apply(this, arguments);
            clearTimeout(this.timer_by_step);
        },
    });


     var accum_productivity_by_step = AbstractField.extend({
        init: function (parent, model, renderer, params) {
            this._super.apply(this, arguments);
        },

        _render: function () {
            this._startTimeCounter();
        },
         _getDateDifference: function (dateStart, dateEnd) {
            return moment(dateEnd).diff(moment(dateStart));
        },
        willStart: function () {
            var self = this;
            self.record_step_id = [];
            var get_productivity;
            var currentDate = new Date();

            var def = rpc.query({
                model: 'time.tracking.actions.wizard',
                method: 'get_time_record',
                args: [this.res_id,this.recordData.key]
            }).then(function (step_ids) {
                   self.duration_by_step = moment(step_ids[0])
                   self.qty_step = step_ids[1]
            });
            return $.when(this._super.apply(this, arguments), def);
        },

        _getDateDifference: function (dateStart, dateEnd) {
                return moment(dateEnd).diff(moment(dateStart));
        },

        isSet: function () {
            return true;
        },


        _startTimeCounter: function () {
            var self = this;
            clearTimeout(this.timer_by_step)
            var mili_segunds = 1000 / self.qty_step
            this.timer_by_step = setTimeout(function () {
                self.duration_by_step += mili_segunds;
                self._startTimeCounter();
                }, 1000);
            this.$el.html($('<span>' + moment.utc(self.duration_by_step).format("HH:mm:ss") + '</span>'));

        },

        destroy: function () {
            this._super.apply(this, arguments);
            clearTimeout(this.timer_by_step);
        },
    });


    var FieldMany2ManyCheckBoxes = AbstractField.extend({
        template: 'One2ManyCheckBoxes',
        events: _.extend({}, AbstractField.prototype.events, {
            change: '_onChange',
//            'click .o_treetable_button_save': 'save_function',
        }),
        specialData: "_fetchSpecialRelation",
        supportedFieldTypes: ['many2many'],
        init: function () {
            this._super.apply(this, arguments);
            this.m2mValues = this.record.specialData[this.name];
        },

       save_function: function () {
            var ids = _.map(this.$('input:checked'), function (input) {
                return $(input).data("record-id");
            });
            var params = [{'analytic_id': ids[0], 'activity_ids': false }]
            self._rpc({
                model: 'time.tracking.actions',
                method: 'create',
                args: params,
                context: this.record.context,
                }).then((records) => {
                    self._rpc({
                    model: 'time.tracking.actions',
                    method: 'finish_activity',
                    args: [records.id, ids[0],this.recordData.activity_ids.data],
                    context: this.record.context,
                    }).then((val) => {

                     this.do_action({type: 'ir.actions.act_window_close'});

                    });
                });
        },

        isSet: function () {
            return true;
        },


        _render: function () {
            var self = this;
            this._super.apply(this, arguments);
            _.each(this.value.res_ids, function (id) {
                self.$('input[data-record-id="' + id + '"]').prop('checked', true);
            });
        },

        _renderReadonly: function () {
            this.$("input").prop("disabled", true);
        },


        _onChange: function () {
            var ids = _.map(this.$('input:checked'), function (input) {
                return $(input).data("record-id");
            });
            this._setValue({
                operation: 'REPLACE_WITH',
                ids: ids,
            });

        },
    });

    var Save_checkboxes_function = AbstractField.extend({

        init: function () {
            this._super.apply(this, arguments);
        },

        save_function (){
            this.FieldMany2ManyCheckBoxes();
        },

        renderButtons: function ($node) {
            var $footer = this.footerToButtons ? this.$('footer') : null;
            var mustRenderFooterButtons = $footer && $footer.length;
            if (!this.defaultButtons && !mustRenderFooterButtons) {
                return;
            }
            this.$buttons = $('<div/>');
            if (mustRenderFooterButtons) {
                this.$buttons.append($footer);

            } else {
                this.$buttons.append(qweb.render("FormView_js.buttons", {widget: this}));

                this.$buttons.on('click', '.o_form_button_create', this._onCreate.bind(this));
                this.$buttons.on('click', '.o_form_button_save', this._onSave.bind(this));
                this._updateButtons();
            }
            this.$buttons.appendTo($node);
        },
    });

    var FieldSelection = AbstractField.extend({
        template: 'FieldSelection',
        specialData: "_fetchSpecialRelation",
        supportedFieldTypes: ['selection', 'many2one'],
        events: _.extend({}, AbstractField.prototype.events, {
            'change': '_onChange',
        }),

        init: function () {
            this._super.apply(this, arguments);
            this._setValues();
        },

        getFocusableElement: function () {
            return this.$el.is('select') ? this.$el : $();
        },

        isSet: function () {
            return this.value !== false;
        },

        updateModifiersValue: function () {
            this._super.apply(this, arguments);
            if (!this.attrs.modifiersValue.invisible && this.mode !== 'readonly') {
                this._setValues();
                this._renderEdit();
            }
        },

        _renderEdit: function () {
            this.$el.empty();
            for (var i = 0 ; i < this.values.length ; i++) {
                this.$el.append($('<option/>', {
                    value: JSON.stringify(this.values[i][0]),
                    text: this.values[i][1]
                }));
            }
            var value = this.value;
            if (this.field.type === 'many2one' && value) {
                value = value.data.id;
            }
            this.$el.val(JSON.stringify(value));
        },

        _renderReadonly: function () {
            this.$el.empty().text(this._formatValue(this.value));
        },

        _reset: function () {
            this._super.apply(this, arguments);
            this._setValues();
        },

        _setValues: function () {
            if (this.field.type === 'many2one') {
                this.values = this.record.specialData[this.name];
                this.formatType = 'many2one';
            } else {
                this.values = _.reject(this.field.selection, function (v) {
                    return v[0] === false && v[1] === '';
                });
            }
            if (!this.attrs.modifiersValue || !this.attrs.modifiersValue.required) {
                this.values = [[false, this.attrs.placeholder || '']].concat(this.values);
            }
        },

        _onChange: function () {
            var res_id = JSON.parse(this.$el.val());
            if (this.field.type === 'many2one') {
                var value = _.find(this.values, function (val) {
                    return val[0] === res_id;
                });
                this._setValue({id: res_id, display_name: value[1]});
            } else {
                this._setValue(res_id);
            }
        },
    });

    var FieldRadio = FieldSelection.extend({
        template: null,
        className: 'o_field_radio',
        tagName: 'span',
        specialData: "_fetchSpecialMany2ones",
        supportedFieldTypes: ['selection', 'many2one'],
        events: _.extend({}, AbstractField.prototype.events, {
            'click input': '_onInputClick',
        }),

        init: function () {
            this._super.apply(this, arguments);
            if (this.mode === 'edit') {
                this.tagName = 'div';
                this.className += this.nodeOptions.horizontal ? ' o_horizontal' : ' o_vertical';
            }
            this.unique_id = _.uniqueId("radio");
            this._setValues();
        },


        isSet: function () {
            return true;
        },

        _renderEdit: function () {
            var self = this;
            var currentValue;
            if (this.field.type === 'many2one') {
                currentValue = this.value && this.value.data.id;

            } else {
                currentValue = this.value;
            }
            this.$el.empty();
            _.each(this.values, function (value, index) {

                self.$el.append(qweb.render('Many2one_Radio', {
                    checked: value[0] === currentValue,
                    id: self.unique_id + '_' + value[0],
                    index: index,
                    value: value,
                }));
            });
        },
        _reset: function () {
            this._super.apply(this, arguments);
            this._setValues();
        },

        _setValues: function () {
            if (this.field.type === 'selection') {
                this.values = this.field.selection || [];
            } else if (this.field.type === 'many2one') {
                this.values = _.map(this.record.specialData[this.name], function (val) {
                    return [val.id, val.display_name];
                });
            }
        },

        _onInputClick: function (event) {
            var index = $(event.target).data('index');
            var value = this.values[index];
            if (this.field.type === 'many2one') {
                this._setValue({id: value[0], display_name: value[1]});
            } else {
                this._setValue(value[0]);
            }
        },
    });


    field_registry
        .add('accum_times', accum_times)
        .add('accum_counter', accum_productivity)
        .add('accum_counter_by_step', accum_productivity_by_step)
        .add('Save_checkboxes', Save_checkboxes_function)
        .add('many2many_ratio', FieldRadio)
        .add('One2Many_checkbox', FieldMany2ManyCheckBoxes);

});
