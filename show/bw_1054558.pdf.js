
    var Component = require("./static/bower_components/pyxley/build/pyxley.js").FilterChart;
    var filter_style = "''";
var dynamic = true;
var charts = [{"type": "MetricsGraphics", "options": {"url": "/hist_static", "chart_id": "line_hist", "params": {"right": 40, "target": "#line_hist", "title": "Histogram", "buffer": 8, "small_width_threshold": 160, "top": 40, "bottom": 30, "height": 300, "width": 600, "chart_type": "histogram", "left": 40, "small_height_threshold": 120, "init_params": {"Data": "Steps"}, "bins": 20, "description": "Histogram"}}}];
var filters = [{"type": "SelectButton", "options": {"default": "Steps", "items": ["Calories Burned", "Steps", "Distance", "Floors", "Minutes Sedentary", "Minutes Lightly Active", "Minutes Fairly Active", "Minutes Very Active", "Activity Calories"], "alias": "Data", "label": "Data"}}, {"type": "SelectButton", "options": {"default": "Steps", "items": ["Calories Burned", "Steps", "Distance", "Floors", "Minutes Sedentary", "Minutes Lightly Active", "Minutes Fairly Active", "Minutes Very Active", "Activity Calories"], "alias": "Data", "label": "Data"}}];
    React.render(
        React.createElement(Component, {
        filter_style: filter_style, 
dynamic: dynamic, 
charts: charts, 
filters: filters}),
        document.getElementById("component_id")
    );
    