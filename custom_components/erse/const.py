"""Constants for the Entidade Reguladora dos Serviços Energéticos integration."""

DOMAIN = "erse"
COUNTRY = "Portugal"
CONF_OPERATOR = "operator"
CONF_PLAN = "plan"
CONF_METER = "meter"
CONF_COST = "cost"
CONF_POWER_COST = "power_cost"
CONF_UTILITY_METER = "utility_meter"
CONF_UTILITY_METERS = "utility_meter"


IVA = 0.23
IVA_REDUZIDA = 0.06
IVA_INTERMEDIA = 0.13
TERMO_FIXO_ACESSO_REDES = 0.2959
TAXA_DGEG = 0.07
IMPOSTO_ESPECIAL_DE_CONSUMO = 0.001
CONTRIB_AUDIOVISUAL = 2.85

DISCOUNT = {
    "Vazio": (40, IVA_INTERMEDIA),
    "Fora de Vazio": (60, IVA_INTERMEDIA),
    "Normal": (100, IVA_INTERMEDIA),
    "Ponta": (42.9, IVA_INTERMEDIA),
    "Cheias": (42.9, IVA_INTERMEDIA),
}
