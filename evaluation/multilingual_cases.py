"""Fixed synthetic bilingual retrieval cases; no personal records are read."""

TOPICS = (
    ("python", "Python", "파이썬", ("Python", "파이썬", "파이선", "Ｐｙｔｈｏｎ", "파이썬으로도", "python으로도")),
    ("api", "API", "에이피아이", ("API", "에이피아이", "에이 피 아이", "ＡＰＩ", "에이피아이를", "api를")),
    ("ml", "machine learning", "기계 학습", ("machine learning", "머신러닝", "머신 러닝", "기계 학습", "머신러닝으로도", "기계 학습으로도")),
    ("kubernetes", "Kubernetes", "쿠버네티스", ("쿠버네티스", "Kubernetes", "쿠버네티스 자료", "Kubernetes 자료", "쿠버네티스 내용", "Kubernetes 내용")),
    ("javascript", "JavaScript", "자바스크립트", ("자바스크립트", "JavaScript", "자바스크립트 자료", "JavaScript 자료", "자바스크립트 내용", "JavaScript 내용")),
    ("receipt", "receipt", "영수증", ("영수증", "receipt", "영수증 자료", "receipt 자료", "영수증 내용", "receipt 내용")),
    ("fridge", "refrigerator", "냉장고", ("냉장고", "refrigerator", "냉장고 자료", "refrigerator 자료", "냉장고 내용", "refrigerator 내용")),
    ("budget", "budget", "예산", ("예산", "budget", "예산 자료", "budget 자료", "예산 내용", "budget 내용")),
    ("ticket", "flight ticket", "항공권", ("항공권", "flight ticket", "항공권 자료", "flight ticket 자료", "항공권 내용", "flight ticket 내용")),
    ("strength", "strength training", "근력 운동", ("근력 운동", "strength training", "근력 운동 자료", "strength training 자료", "근력 운동 내용", "strength training 내용")),
)

CONTRASTS = (
    ("cpp", "C++", ("C++", "C++ 자료", "C++ 내용")),
    ("csharp", "C#", ("C#", "C# 자료", "C# 내용")),
    ("dotnet", ".NET", (".NET", ".NET 자료", ".NET 내용")),
    ("node", "Node.js", ("Node.js", "Node.js 자료", "Node.js 내용")),
    ("java", "Java 프로그래밍 언어", ("자바 프로그래밍", "Java 언어", "Java 개발")),
    ("code", "code review 코드 리뷰", ("코드 리뷰", "code review", "개발 코드 리뷰")),
    ("pythonista", "pythonista", ("pythonista", "pythonista 자료", "pythonista 내용")),
    ("person", "민수가 Python 자료를 정리했다", ("민수 Python", "민수 파이썬", "민수 파이선")),
    ("dated", "Python 자료", ("2026-10-01 Python", "2026-10-01 파이썬", "2026-10-01 파이선")),
    ("negation", "API 배포를 하지 않았다", ("API 배포 부정", "에이피아이 배포 부정", "에이 피 아이 배포 부정")),
)


def dataset():
    documents, cases = [], []
    for topic, english, korean, questions in TOPICS:
        # Both directions: four records use each language; all eight are relevant.
        for index in range(8):
            label = english if index % 2 == 0 else korean
            documents.append({"id": f"{topic}-{index}", "topic": topic,
                              "text": f"{label} 관련 자료와 내용을 정리했다. 문서 {index}."})
        for index, question in enumerate(questions):
            cases.append({"id": f"positive-{topic}-{index}", "group": "positive",
                          "question": question, "topics": [topic]})
    for topic, text, questions in CONTRASTS:
        for index in range(8):
            document = {"id": f"{topic}-{index}", "topic": topic,
                        "text": f"{text}. 관련 자료와 내용을 정리했다. 문서 {index}."}
            if topic == "person":
                document["actor"] = "민수"
            if topic == "dated":
                document["date"] = "2026-10-01"
            if topic == "negation":
                document["state"] = "negated"
            documents.append(document)
        for index, question in enumerate(questions):
            # A bare Python/API question also legitimately retrieves these topics.
            topics = [topic]
            if topic == "person":
                topics = ["person"]
            cases.append({"id": f"negative-{topic}-{index}", "group": "negative",
                          "question": question, "topics": topics})
    for topic, text in (("c", "C 언어"), ("net", "net 그물"), ("nodewords", "node js 별개의 단어"),
                        ("island", "Java island 자바섬 여행"), ("chord", "chord progression 코드 진행 화음 음악"),
                        ("cord", "cord 전선 연결"), ("person-other", "지연이가 Python 자료를 정리했다")):
        for index in range(8):
            documents.append({"id": f"{topic}-{index}", "topic": topic,
                              "text": f"{text}. 관련 자료와 내용을 정리했다. 문서 {index}.",
                              **({"actor": "지연"} if topic == "person-other" else {})})
    # Unconstrained positive searches consider all matching records relevant.
    for case in cases:
        if case["group"] == "positive" and case["topics"] == ["python"]:
            case["topics"] += ["person", "person-other", "dated"]
        if case["group"] == "positive" and case["topics"] == ["api"]:
            case["topics"].append("negation")
    return documents, cases
