from src.data.player_impact import compute_player_impact_from_stats


def test_player_impact_salah():
    salah_stats = {
        "player_id": 11,
        "minutes": 3000,
        "xg": 20.0,
        "xa": 12.0,
        "key_passes": 80,
        "progressive_passes": 120,
        "tackles": 30,
        "interceptions": 15,
    }
    replacement_stats = {
        "player_id": 12,
        "minutes": 1500,
        "xg": 5.0,
        "xa": 4.0,
        "key_passes": 30,
        "progressive_passes": 40,
        "tackles": 15,
        "interceptions": 5,
    }

    impact = compute_player_impact_from_stats(salah_stats, replacement_stats)

    assert impact["xg_per90"] == 0.6
    assert impact["xa_per90"] == 0.36
    assert impact["offensive_impact"] == 0.96
    assert impact["replacement_delta"]["xg_per90"] == 0.3


def test_player_impact_haaland():
    haaland_stats = {
        "player_id": 9,
        "minutes": 2800,
        "xg": 28.0,
        "xa": 5.0,
        "key_passes": 25,
        "progressive_passes": 30,
        "tackles": 8,
        "interceptions": 6,
    }
    replacement_stats = {
        "player_id": 19,
        "minutes": 1200,
        "xg": 8.0,
        "xa": 2.0,
        "key_passes": 10,
        "progressive_passes": 12,
        "tackles": 4,
        "interceptions": 3,
    }

    impact = compute_player_impact_from_stats(haaland_stats, replacement_stats)

    assert impact["xg_per90"] == 0.9
    assert impact["xa_per90"] == 0.161
    assert impact["offensive_impact"] == 1.061
    assert impact["replacement_delta"]["offensive_impact"] == 0.311


def test_player_impact_van_dijk():
    van_dijk_stats = {
        "player_id": 4,
        "minutes": 3200,
        "xg": 3.0,
        "xa": 1.0,
        "key_passes": 20,
        "progressive_passes": 60,
        "tackles": 50,
        "interceptions": 45,
    }
    replacement_stats = {
        "player_id": 14,
        "minutes": 1800,
        "xg": 1.0,
        "xa": 0.5,
        "key_passes": 12,
        "progressive_passes": 35,
        "tackles": 20,
        "interceptions": 15,
    }

    impact = compute_player_impact_from_stats(van_dijk_stats, replacement_stats)

    assert impact["tackles_per90"] == 1.406
    assert impact["interceptions_per90"] == 1.266
    assert impact["defensive_impact"] == 2.672
    assert impact["replacement_delta"]["defensive_impact"] == 0.922
