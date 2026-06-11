declare module "encoding-japanese" {
  interface EncodingApi {
    detect(data: string | number[] | Uint8Array): string | false;
    convert(
      data: string | number[] | Uint8Array,
      options: { to: string; from?: string; type: "string" },
    ): string;
    convert(
      data: string | number[] | Uint8Array,
      options: { to: string; from?: string; type: "array" },
    ): number[];
  }

  const Encoding: EncodingApi;
  export default Encoding;
}
