from homeassistant import config_entries
from homeassistant.helpers import selector
import voluptuous as vol

class LiveBoardConfigFlow(config_entries.ConfigFlow, domain="tiny_liveboard"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Tiny LiveBoard", data=user_input)
        schema = vol.Schema({
            vol.Optional("camera0"): selector.EntitySelector(selector.EntitySelectorConfig(domain="camera")),
            vol.Optional("camera1"): selector.EntitySelector(selector.EntitySelectorConfig(domain="camera")),
            vol.Optional("weather"): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        })
        return self.async_show_form(step_id="user", data_schema=schema)
