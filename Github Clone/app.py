from flask import Flask, render_template, request, jsonify
from calculator import perform_calculation

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
	return render_template("index.html")


@app.route("/calculate", methods=["POST"])
def calculate():
	try:
		# Accepts form-encoded input named "input"
		input_value = request.form.get("input", type=float)
		result = perform_calculation(input_value)
		return jsonify({"ok": True, "result": result})
	except Exception as exc:
		return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
	app.run(debug=True)
