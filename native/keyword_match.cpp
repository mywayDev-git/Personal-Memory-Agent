// CPython C++ prototype: retain CPython Unicode/casefold semantics and offsets.
// No model, database, or source-text logging. GIL is held for Python C API calls.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <new>
#include <thread>
#include <utility>
#include <vector>

namespace {
struct PythonError {};
struct Ref {
    PyObject* value;
    explicit Ref(PyObject* p = nullptr) : value(p) {}
    ~Ref() { Py_XDECREF(value); }
    Ref(const Ref& r) : value(Py_XNewRef(r.value)) {}
    Ref(Ref&& r) noexcept : value(std::exchange(r.value, nullptr)) {}
    Ref& operator=(Ref r) noexcept { std::swap(value, r.value); return *this; }
};
PyObject* checked(PyObject* p) { if (!p) throw PythonError{}; return p; }
PyObject* item(PyObject* dict, const char* name) {
    if (!PyDict_Check(dict)) {
        PyErr_SetString(PyExc_TypeError, "expected a dictionary");
        throw PythonError{};
    }
    auto* value = PyDict_GetItemString(dict, name);
    if (!value) { PyErr_SetString(PyExc_KeyError, name); throw PythonError{}; }
    return value;
}
void unicode(PyObject* value) {
    if (!PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "expected Unicode text");
        throw PythonError{};
    }
}
struct Token { Py_ssize_t start, end; Ref quote, folded; };

PyObject* match_batch(PyObject*, PyObject* args) {
    PyObject *input, *term_input, *vocabulary, *normalize;
    if (!PyArg_ParseTuple(args, "OOOO:match_batch", &input, &term_input, &vocabulary, &normalize))
        return nullptr;
    if (!PyCallable_Check(normalize)) {
        PyErr_SetString(PyExc_TypeError, "normalize must be callable");
        return nullptr;
    }
    try {
        Ref rows(checked(PySequence_Fast(input, "rows must be a sequence")));
        Ref terms(checked(PySequence_Fast(term_input, "terms must be a sequence")));
        Ref norm_cache(checked(PyDict_New()));
        Ref expressions(checked(PyImport_ImportModule("pma.search_explain")));
        Ref tokenizer(checked(PyObject_GetAttrString(expressions.value, "token_spans")));
        Ref result(checked(PyList_New(0)));
        const char* names[] = {"term", "kind", "field", "start", "end", "quote"};
        std::vector<Ref> keys;
        for (auto name : names) keys.emplace_back(checked(PyUnicode_InternFromString(name)));
        Ref source_field(checked(PyUnicode_InternFromString("source_text")));
        Ref content_field(checked(PyUnicode_InternFromString("content")));
        Ref exact_kind(checked(PyUnicode_InternFromString("exact")));
        Ref normalized_kind(checked(PyUnicode_InternFromString("normalized")));
        std::vector<std::pair<PyObject*, PyObject*>> parsed_terms;
        for (Py_ssize_t j = 0; j < PySequence_Fast_GET_SIZE(terms.value); ++j) {
            auto* term = PySequence_Fast_GET_ITEM(terms.value, j);
            auto* text = item(term, "text"); auto* normal = item(term, "normalized");
            unicode(text); unicode(normal); parsed_terms.emplace_back(text, normal);
        }
        for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(rows.value); ++i) {
            if ((i & 127) == 0) {
                if (PyErr_CheckSignals() < 0) throw PythonError{};
                Py_BEGIN_ALLOW_THREADS
                std::this_thread::yield();
                Py_END_ALLOW_THREADS
            }
            auto* row = PySequence_Fast_GET_ITEM(rows.value, i);
            PyObject* texts[] = {item(row, "text"), item(item(row, "memory"), "content")};
            PyObject* fields[] = {source_field.value, content_field.value};
            Ref matches(checked(PyList_New(0)));
            for (int field = 0; field < 2; ++field) {
                auto* text = texts[field]; unicode(text);
                // Share token boundaries, width folding and original offsets with Python.
                Ref spans(checked(PyObject_CallOneArg(tokenizer.value, text)));
                Ref sequence(checked(PySequence_Fast(spans.value, "token spans must be a sequence")));
                std::vector<Token> tokens;
                for (Py_ssize_t j = 0; j < PySequence_Fast_GET_SIZE(sequence.value); ++j) {
                    auto* span = PySequence_Fast_GET_ITEM(sequence.value, j);
                    auto start = PyLong_AsSsize_t(PyTuple_GetItem(span, 0));
                    auto end = PyLong_AsSsize_t(PyTuple_GetItem(span, 1));
                    if (PyErr_Occurred()) throw PythonError{};
                    Ref quote(Py_NewRef(checked(PyTuple_GetItem(span, 2))));
                    Ref folded(Py_NewRef(checked(PyTuple_GetItem(span, 3))));
                    unicode(quote.value); unicode(folded.value);
                    tokens.push_back(Token{start, end, std::move(quote), std::move(folded)});
                }
                for (const auto& parsed : parsed_terms) {
                    auto* term = parsed.first;
                    auto* normalized_term = parsed.second;
                    auto append = [&](const Token& token, PyObject* match_kind) {
                        Ref found(checked(PyDict_New()));
                        Ref start(checked(PyLong_FromSsize_t(token.start)));
                        Ref end(checked(PyLong_FromSsize_t(token.end)));
                        PyObject* values[] = {term, match_kind, fields[field], start.value,
                                              end.value, token.quote.value};
                        for (int k = 0; k < 6; ++k)
                            if (PyDict_SetItem(found.value, keys[k].value, values[k]) < 0)
                                throw PythonError{};
                        if (PyList_Append(matches.value, found.value) < 0) throw PythonError{};
                    };
                    bool exact = false;
                    for (const auto& token : tokens) {
                        if (PyUnicode_Compare(token.folded.value, term) == 0) {
                            append(token, exact_kind.value); exact = true;
                        }
                    }
                    if (exact) continue;
                    for (const auto& token : tokens) {
                        Ref normalized;
                        auto* cached = PyDict_GetItemWithError(norm_cache.value, token.folded.value);
                        if (cached) normalized = Ref(Py_NewRef(cached));
                        else {
                            if (PyErr_Occurred()) throw PythonError{};
                            normalized = Ref(checked(PyObject_CallFunctionObjArgs(
                                normalize, token.folded.value, vocabulary, nullptr)));
                            unicode(normalized.value);
                            if (PyDict_Size(norm_cache.value) < 16384 && PyDict_SetItem(
                                norm_cache.value, token.folded.value, normalized.value) < 0)
                                throw PythonError{};
                        }
                        if (PyUnicode_Compare(normalized.value, normalized_term) == 0)
                            append(token, normalized_kind.value);
                    }
                }
            }
            if (PyList_Append(result.value, matches.value) < 0) throw PythonError{};
        }
        return Py_NewRef(result.value);
    } catch (const PythonError&) { return nullptr; }
      catch (const std::bad_alloc&) { return PyErr_NoMemory(); }
      catch (...) { PyErr_SetString(PyExc_RuntimeError, "native keyword matching failed"); return nullptr; }
}
PyMethodDef methods[] = {
    {"match_batch", match_batch, METH_VARARGS, "Match rows using CPython Unicode semantics."},
    {nullptr, nullptr, 0, nullptr}
};
PyModuleDef module = {PyModuleDef_HEAD_INIT, "_keyword_native", nullptr, -1, methods};
PyModuleDef expressions_module = {PyModuleDef_HEAD_INIT, "_keyword_native_expressions", nullptr, -1, methods};
PyObject* initialize(PyModuleDef* definition) {
    auto* result = PyModule_Create(definition);
    if (result && PyModule_AddIntConstant(result, "TOKENIZER_VERSION", 1) < 0) {
        Py_DECREF(result); return nullptr;
    }
    return result;
}
}
PyMODINIT_FUNC PyInit__keyword_native() { return initialize(&module); }
PyMODINIT_FUNC PyInit__keyword_native_expressions() { return initialize(&expressions_module); }
