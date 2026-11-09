// In the web dashboard, React comes from the plugin SDK; plugins must never bundle their own copy.
const React = window.__HERMES_PLUGIN_SDK__.React
export default React
