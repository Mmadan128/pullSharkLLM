import pathway as pw

value_functions = {
    'number': lambda x: x + 1,
    # f used to tell string containse variable
    'name': lambda x: f'Person {x}',
    'age': lambda x: 20 + x,
}

class InputSchema(pw.Schema):
    number: int
    name: str
    age: int

table = pw.demo.generate_custom_stream(value_functions, schema=InputSchema, nb_rows=10)

pw.debug.compute_and_print(table)
