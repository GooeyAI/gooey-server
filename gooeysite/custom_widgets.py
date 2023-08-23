from django import forms


class JSONEditorWidget(forms.Textarea):
    def __init__(self):
        super().__init__({"class": "jsoneditor"})

    class Media:
        js = [
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/codemirror.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/mode/javascript/javascript.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/addon/lint/lint.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/addon/lint/javascript-lint.min.js",
            "https://unpkg.com/jshint@2.13.2/dist/jshint.js",
        ]
        css = {
            "all": [
                "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/codemirror.min.css",
                "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/theme/monokai.min.css",
                "https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/addon/lint/lint.min.css",
            ]
        }
