from types import SimpleNamespace

from db_manager import Database


def test_apply_sample_keyword_reclassifies_existing_non_manual_folders(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(classification_history_file=str(tmp_path / "classification_history.txt")),
    )

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, r"D:\Photos\希威社\001.jpg", "001.jpg", r"D:\Photos\希威社", "希威社"),
        )
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (2, r"D:\Photos\Manual\希威社\002.jpg", "002.jpg", r"D:\Photos\Manual\希威社", "希威社"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, ?)",
            (r"D:\Photos\希威社", "fallback"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, ?)",
            (r"D:\Photos\Manual\希威社", "manual"),
        )

    changed = classifier.apply_keyword_to_existing_folders("希威社", classifier.CATEGORY_SAMPLE)

    with db.connect() as conn:
        auto_cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (r"D:\Photos\希威社",),
        ).fetchone()[0]
        manual_cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (r"D:\Photos\Manual\希威社",),
        ).fetchone()[0]

    assert changed == 1
    assert auto_cat == classifier.CATEGORY_SAMPLE
    assert manual_cat == classifier.CATEGORY_LIFE


def test_refine_sample_keyword_uses_normalized_unc_source_branch(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=r"\crh\homes\waxzml\Photos",
            source_dirs=[r"\\crh\homes\waxzml\Photos"],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    folder_path = r"\\crh\homes\waxzml\Photos\希威社\NO.009\2021\06"
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (
                1,
                folder_path + r"\001.jpg",
                "iphone_001.jpg",
                folder_path,
                "06",
            ),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, 1, ?)",
            (folder_path, "keyword-refine"),
        )

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert refined == 1
    assert cat == classifier.CATEGORY_SAMPLE


def test_refine_keywords_prefers_specific_sample_child_over_life_parent(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    folder = source / "FilmOutput" / "SampleCollect" / "Set001"
    folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    folder_path = str(folder)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, str(folder / "001.jpg"), "001.jpg", folder_path, "Set001"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (folder_path, classifier.CATEGORY_LIFE, "keyword-refine"),
        )
        conn.execute("INSERT INTO sample_keywords (keyword) VALUES (?)", ("SampleCollect",))
        conn.execute("INSERT INTO life_keywords (keyword) VALUES (?)", ("FilmOutput",))

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert refined == 1
    assert cat == classifier.CATEGORY_SAMPLE


def test_refine_keywords_keeps_mobile_backup_tree_as_life(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    folder = source / "MobileBackup" / "SampleCollect" / "Set001"
    folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    folder_path = str(folder)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, str(folder / "001.jpg"), "001.jpg", folder_path, "Set001"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (folder_path, classifier.CATEGORY_SAMPLE, "keyword-refine"),
        )
        conn.execute("INSERT INTO sample_keywords (keyword) VALUES (?)", ("SampleCollect",))

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert refined == 1
    assert cat == classifier.CATEGORY_LIFE


def test_refine_keywords_keeps_moments_tree_as_life(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    folder = source / "Moments" / "NSFW" / "Set001"
    folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    folder_path = str(folder)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, str(folder / "001.jpg"), "001.jpg", folder_path, "Set001"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (folder_path, classifier.CATEGORY_SAMPLE, "manual"),
        )

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert refined == 1
    assert cat == classifier.CATEGORY_LIFE


def test_refine_keywords_keeps_film_output_life_tree_as_life(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    folder = source / "胶片成图" / "日常生活" / "随便"
    folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    folder_path = str(folder)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
            (1, str(folder / "heliar-5294-5.jpg"), "heliar-5294-5.jpg", folder_path, "随便"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (folder_path, classifier.CATEGORY_SAMPLE, "manual"),
        )

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert refined == 1
    assert cat == classifier.CATEGORY_LIFE


def test_refine_keywords_treats_adult_source_tree_as_sample(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    folders = [
        source / "电报色图" / "Set001",
        source / "NW" / "Set002",
        source / "NSFW" / "Set003",
    ]
    for folder in folders:
        folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
        ),
    )

    with db.connect() as conn:
        for idx, folder in enumerate(folders, start=1):
            folder_path = str(folder)
            conn.execute(
                "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, is_image) VALUES (?, ?, ?, ?, ?, 1)",
                (idx, str(folder / f"{idx}.jpg"), f"{idx}.jpg", folder_path, folder.name),
            )
            conn.execute(
                "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
                (folder_path, classifier.CATEGORY_LIFE, "llm-branch"),
            )

    refined = classifier.refine_sample_keywords()

    with db.connect() as conn:
        cats = [
            conn.execute(
                "SELECT category FROM folder_categories WHERE folder_path = ?",
                (str(folder),),
            ).fetchone()[0]
            for folder in folders
        ]

    assert refined == 3
    assert cats == [classifier.CATEGORY_SAMPLE] * 3


def test_classify_folders_treats_mobile_backup_source_root_as_life(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "MobileBackup"
    folder = source / "2024" / "06"
    folder.mkdir(parents=True)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
            deepseek_classify_model="test",
        ),
    )

    folder_path = str(folder)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (1, str(folder / "001.jpg"), "001.jpg", folder_path, "06", 1, "2024-06-01T00:00:00"),
        )

    def fail_llm(_branch_info):
        raise AssertionError("MobileBackup source should be classified by keyword before LLM")

    monkeypatch.setattr(classifier, "classify_branches_with_llm", fail_llm)

    result = classifier.classify_folders()

    with db.connect() as conn:
        cat = conn.execute(
            "SELECT category FROM folder_categories WHERE folder_path = ?",
            (folder_path,),
        ).fetchone()[0]

    assert result["llm_queued"] == 0
    assert cat == classifier.CATEGORY_LIFE


def test_classify_folders_reuses_current_fingerprint_without_llm(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    branch = source / "Other"
    branch.mkdir(parents=True)
    folder_path = str(branch)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
            deepseek_classify_model="test",
        ),
    )

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (1, str(branch / "a.jpg"), "a.jpg", folder_path, "Other", 1, "2024-01-01T00:00:00"),
        )

    fp = classifier.build_folder_fingerprint(folder_path)
    classifier.set_folder_category(folder_path, classifier.CATEGORY_LIFE, "llm-branch", fingerprint=fp["fingerprint"])

    def fail_llm(_branch_info):
        raise AssertionError("LLM should not be called when fingerprint is current")

    monkeypatch.setattr(classifier, "classify_branches_with_llm", fail_llm)

    result = classifier.classify_folders()

    assert result["llm_queued"] == 0
    assert result["skipped"] == 1


def test_classify_folders_dirty_fingerprint_calls_llm(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    branch = source / "Other"
    branch.mkdir(parents=True)
    folder_path = str(branch)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
            deepseek_classify_model="test",
        ),
    )

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (1, str(branch / "a.jpg"), "a.jpg", folder_path, "Other", 1, "2024-01-01T00:00:00"),
        )

    fp = classifier.build_folder_fingerprint(folder_path)
    classifier.set_folder_category(folder_path, classifier.CATEGORY_LIFE, "llm-branch", fingerprint=fp["fingerprint"])

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (2, str(branch / "b.jpg"), "b.jpg", folder_path, "Other", 1, "2024-02-01T00:00:00"),
        )

    calls = []

    def fake_llm(branch_info):
        calls.append(branch_info)
        return {"Other": classifier.CATEGORY_SAMPLE}

    monkeypatch.setattr(classifier, "classify_branches_with_llm", fake_llm)

    result = classifier.classify_folders()

    assert result["llm_queued"] == 1
    assert len(calls) == 1
    with db.connect() as conn:
        row = conn.execute("SELECT category, status, fingerprint FROM folder_categories WHERE folder_path = ?", (folder_path,)).fetchone()
    assert row["category"] == classifier.CATEGORY_SAMPLE
    assert row["status"] == "ok"
    assert row["fingerprint"] == classifier.build_folder_fingerprint(folder_path)["fingerprint"]


def test_classify_folders_backfills_missing_fingerprint_without_llm(tmp_path, monkeypatch):
    from business.classifier import folder_classifier as classifier

    db = Database(str(tmp_path / "photos.db"))
    db.init_tables()
    source = tmp_path / "Photos"
    branch = source / "Other"
    branch.mkdir(parents=True)
    folder_path = str(branch)
    monkeypatch.setattr(classifier, "_db", db)
    monkeypatch.setattr(
        classifier,
        "get_settings",
        lambda: SimpleNamespace(
            source_drive=str(source),
            source_dirs=[str(source)],
            classification_history_file=str(tmp_path / "classification_history.txt"),
            deepseek_classify_model="test",
        ),
    )

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO files (id, file_path, file_name, folder_path, folder_name, file_size, file_mtime, is_image) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (1, str(branch / "a.jpg"), "a.jpg", folder_path, "Other", 1, "2024-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO folder_categories (folder_path, category, confidence) VALUES (?, ?, ?)",
            (folder_path, classifier.CATEGORY_LIFE, "llm-branch"),
        )

    def fail_llm(_branch_info):
        raise AssertionError("LLM should not be called for trusted old category without fingerprint")

    monkeypatch.setattr(classifier, "classify_branches_with_llm", fail_llm)

    result = classifier.classify_folders()

    assert result["llm_queued"] == 0
    assert result["skipped"] == 1
    with db.connect() as conn:
        row = conn.execute("SELECT fingerprint, status FROM folder_categories WHERE folder_path = ?", (folder_path,)).fetchone()
    assert row["fingerprint"]
    assert row["status"] == "ok"
