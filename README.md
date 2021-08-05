# ha_erse
Home Assistant Custom Component for ERSE (Entidade Reguladora dos Serviços Energéticos)

This component provides the current tariff of a given electricity operator as well as a simulation of the costs associated.

This components is for energy clients in Portugal, and fully automates the transitions of tariffs of a utility_meter.

# Configuration

Go to **Configuration** >> **Integrations** in the UI. Click the button with `+` sign on the integrations page and from the list of integrations, select **ERSE**.

Type in your Energy Provider (EDP, GALP, Iberdrola), Power installed and the tariff plan and cycle (default is Ciclo Diário).

Then select which `utility_meters` are running through this electricity plan (this is optional and is only necessary to automate tariff change of the `utility_meter`)

Finally you must type in the cost in Euros of power availability and tariffs (Euro/kWh) as well as the entities that track each tariff.

**Important**

Your `utility_meter` must have the proper tarifs:
- Bi-Horário: `Vazio` e `Fora de Vazio`
- Tri-Horário: `Vazio`, `Ponta` e `Cheias`

That is it!

# Help

Join me at [CPHA Discord](https://discord.gg/Mh9mTEA)
