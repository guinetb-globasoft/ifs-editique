from decimal import Decimal

from app.rendu.formats import date_fr, montant_euros, nombre

NBSP = " "


def test_nombre_a_la_francaise_comme_armony():
    assert nombre(2000) == f"2{NBSP}000,00"
    assert nombre(Decimal("1234567.891")) == f"1{NBSP}234{NBSP}567,89"
    assert nombre(1) == "1,00"
    assert nombre(0) == "0,00"
    assert nombre(-1500.5) == f"-1{NBSP}500,50"


def test_nombre_absent_n_imprime_rien():
    assert nombre(None) == ""
    assert montant_euros(None) == ""


def test_arrondi_au_plus_proche_et_non_bancaire():
    assert nombre(Decimal("0.125")) == "0,13"
    assert nombre(Decimal("2.675")) == "2,68"


def test_montant_total():
    assert montant_euros(2000) == f"2{NBSP}000,00{NBSP}€"


def test_date_sans_conversion_de_fuseau():
    assert date_fr("2026-10-14") == "14/10/2026"
    # Sans l'en-tête fuseau, IFS rend la valeur enregistrée : on ne la décale pas.
    assert date_fr("2026-10-14T00:00:00Z") == "14/10/2026"
    assert date_fr(None) == ""
    assert date_fr("") == ""
