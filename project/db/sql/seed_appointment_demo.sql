INSERT INTO departments (code, name, description)
VALUES
    ('resp', '呼吸内科', '呼吸系统相关门诊'),
    ('cardio', '心内科', '心血管相关门诊'),
    ('general', '全科医学科', '常见病初诊与分诊')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO doctors (department_id, name, title, profile)
SELECT d.id, seed.name, seed.title, seed.profile
FROM (
    VALUES
        ('resp', '张医生', '主治医师', '擅长常见呼吸系统疾病'),
        ('cardio', '李医生', '副主任医师', '擅长常见心血管疾病'),
        ('general', '王医生', '主治医师', '擅长常见病初诊和分流')
) AS seed(code, name, title, profile)
JOIN departments d ON d.code = seed.code
WHERE NOT EXISTS (
    SELECT 1 FROM doctors existing
    WHERE existing.department_id = d.id AND existing.name = seed.name
);

INSERT INTO doctor_schedules (doctor_id, department_id, schedule_date, time_slot, quota_total, quota_available)
SELECT doc.id, doc.department_id, seed.schedule_date, seed.time_slot, 10, 10
FROM (
    SELECT doctor_name, schedule_date::date, time_slot
    FROM (
        SELECT '张医生' AS doctor_name, gs::date AS schedule_date, 'afternoon' AS time_slot
        FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '3 day', INTERVAL '1 day') AS gs
        UNION ALL
        SELECT '张医生', gs::date, 'morning'
        FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '3 day', INTERVAL '1 day') AS gs
        UNION ALL
        SELECT '李医生', gs::date, 'afternoon'
        FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '3 day', INTERVAL '1 day') AS gs
        UNION ALL
        SELECT '王医生', gs::date, 'morning'
        FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '3 day', INTERVAL '1 day') AS gs
    ) t
) AS seed(doctor_name, schedule_date, time_slot)
JOIN doctors doc ON doc.name = seed.doctor_name
WHERE NOT EXISTS (
    SELECT 1 FROM doctor_schedules ds
    WHERE ds.doctor_id = doc.id
      AND ds.schedule_date = seed.schedule_date::date
      AND ds.time_slot = seed.time_slot
);
